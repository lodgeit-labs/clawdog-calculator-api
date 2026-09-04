"""Central engine-error-mapper tests.

Fable post-matrix directive mc00-2026-09-04, D8a + D8b + Amendments 1-4:

  * D8a — engine 4xx must never surface as gateway 5xx (partition on
    whose fault, not on the digit — Amendment 1).
  * D8b — the error surface is part of the contract; strip `numeric_mode`
    (Amendment 2 rider 2) and `events` (§A2.2 10 000-item affordance).
  * Amendment 1 — fault-based 4xx partition:
      caller-fault (400/409/413/422) → same 4xx re-emit with detail
      gateway-fault (401/403/404/405) → 502 (our misconfiguration)
      rate-limit (429) → 503 (caller retryable) + Retry-After
  * Amendment 2 — engine_timeout = 504, not 503 (request sent, engine
    did not respond in time = Gateway Timeout, textbook).
  * Amendment 3 — 422 branch emits `gateway_engine_schema_drift` log
    once defence-in-depth lands; the log is the drift-detector.
  * Fable §6 cosmetic — refusal envelope flat, no `{"detail": {"detail":
    {...}}}` nesting.
"""
from __future__ import annotations

import json
import logging

import pytest

from api.lib.engine_error_mapper import (
    _sanitise_engine_body,
    map_calculation_error_to_http,
    map_engine_error_to_http,
)
from api.prolog_client import PrologCalculationError, PrologEngineUnavailable

# ============================================================================
# D8b — sanitisation primitives
# ============================================================================


def test_sanitise_strips_numeric_mode_from_dict():
    body = {"basis": "accounting", "numeric_mode": "serving", "cost": 5000}
    out = _sanitise_engine_body(body)
    assert "numeric_mode" not in out
    assert out == {"basis": "accounting", "cost": 5000}


def test_sanitise_strips_events_from_dict():
    body = {"basis": "accounting", "events": [{"event": "cost_addition"}]}
    out = _sanitise_engine_body(body)
    assert "events" not in out
    assert out == {"basis": "accounting"}


def test_sanitise_strips_both_from_nested_request_key():
    body = {
        "error": "validation",
        "request": {
            "basis": "accounting",
            "numeric_mode": "serving",
            "events": [],
        },
    }
    out = _sanitise_engine_body(body)
    assert out["request"] == {"basis": "accounting"}


def test_sanitise_strips_from_json_string():
    body_str = json.dumps(
        {"error": "validation", "numeric_mode": "serving", "events": []}
    )
    out = _sanitise_engine_body(body_str)
    parsed = json.loads(out)
    assert "numeric_mode" not in parsed
    assert "events" not in parsed
    assert parsed == {"error": "validation"}


def test_sanitise_leaves_non_json_string_unchanged():
    text = "internal engine failure at line 42"
    out = _sanitise_engine_body(text)
    assert out == text


def test_sanitise_preserves_all_other_fields():
    body = {
        "basis": "accounting",
        "asset": {"cost": "5000.00"},
        "detail": "asset.tax_asset_class required",
        "field": "asset.tax_asset_class",
    }
    out = _sanitise_engine_body(body)
    assert out == body


# ============================================================================
# Amendment 1 (caller-fault) — engine 4xx caller-content → gateway same 4xx
# ============================================================================


def test_engine_422_maps_to_gateway_422_with_detail(caplog):
    """The first tester's most likely mistake — omitting
    `accounting_useful_life_years` — must surface as 422 with actionable
    engine detail, NOT 502 `engine_unavailable`."""
    engine_body = json.dumps(
        {
            "error": "validation",
            "field": "asset.accounting_useful_life_years",
            "detail": "basis='accounting' requires 'asset.accounting_useful_life_years'",
        }
    )
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 422, "body": engine_body},
        engine="depreciation",
        url="http://dep-engine.test/v1/calculators/depreciation/at/urn:...",
    )
    with caplog.at_level(logging.WARNING, logger="api.lib.engine_error_mapper"):
        http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 422
    assert http_exc.detail["error"] == "engine_validation_error"
    assert http_exc.detail["status_code"] == 422
    assert http_exc.detail["engine"] == "depreciation"
    engine_detail = http_exc.detail["engine_detail"]
    assert isinstance(engine_detail, dict)
    assert engine_detail["field"] == "asset.accounting_useful_life_years"


def test_engine_422_emits_drift_detector_log(caplog):
    """Amendment 3: engine 422 firing at all means the gateway schema is
    behind the engine's. Log the drift as a distinct observable event."""
    engine_body = json.dumps(
        {"error": "validation", "detail": "some new engine rule"}
    )
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 422, "body": engine_body},
        engine="depreciation",
        url="http://dep-engine.test",
    )
    with caplog.at_level(logging.WARNING, logger="api.lib.engine_error_mapper"):
        map_engine_error_to_http(exc)
    assert any(
        "gateway_engine_schema_drift" in rec.message for rec in caplog.records
    ), f"expected drift-detector log line; got: {[r.message for r in caplog.records]}"


def test_engine_422_sanitises_leaked_internal_fields():
    """D8b: engine echoes `numeric_mode` / `events` back in its 422 body;
    mapper strips before surfacing."""
    engine_body = json.dumps(
        {
            "error": "validation",
            "detail": "basis='accounting' requires 'asset.accounting_useful_life_years'",
            "numeric_mode": "serving",
            "events": [],
        }
    )
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 422, "body": engine_body},
        engine="depreciation",
        url="http://dep-engine.test",
    )
    http_exc = map_engine_error_to_http(exc)
    engine_detail = http_exc.detail["engine_detail"]
    assert "numeric_mode" not in engine_detail
    assert "events" not in engine_detail


def test_engine_400_without_refusal_class_maps_to_gateway_400():
    """Bare-400 arm has a real producer:
    depreciation-engine routes.py:860 emits 400 without `refusal_class` on
    `to_date < acquisition_date` at `/range/`. Fable Amendment 4 grep
    proved the arm is not artefact-with-no-producer.
    """
    engine_body = json.dumps(
        {"error": "malformed_input", "detail": "at_date is not a valid ISO date"}
    )
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 400, "body": engine_body},
        engine="depreciation",
        url="http://dep-engine.test",
    )
    http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 400
    assert http_exc.detail["error"] == "engine_bad_request"


def test_engine_409_maps_to_gateway_409():
    """Caller-fault 4xx set includes 409 (conflict — caller's data conflicts
    with engine state)."""
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 409, "body": '{"detail":"version conflict"}'},
        engine="depreciation",
        url="http://dep-engine.test",
    )
    http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 409
    assert http_exc.detail["error"] == "engine_conflict"


def test_engine_413_maps_to_gateway_413():
    """Caller-fault 4xx set includes 413 (payload too large — caller sent
    too many events)."""
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 413, "body": '{"detail":"events > 10000"}'},
        engine="depreciation",
        url="http://dep-engine.test",
    )
    http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 413
    assert http_exc.detail["error"] == "engine_payload_too_large"


# ============================================================================
# Amendment 1 (gateway-fault) — engine 401/403/404/405 → gateway 502
# ============================================================================


@pytest.mark.parametrize("engine_status", [401, 403])
def test_engine_auth_failure_maps_to_gateway_502(engine_status, caplog):
    """Approach-D readiness (Fable Amendment 1): when engines close to IAM
    invoker binding, an unbound gateway gets 401/403 from the engine. The
    mapper must NOT tell every caller they are forbidden — this is OUR
    misconfiguration."""
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": engine_status, "body": "Unauthorized"},
        engine="depreciation",
        url="http://dep-engine.test",
    )
    with caplog.at_level(logging.ERROR, logger="api.lib.engine_error_mapper"):
        http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 502, (
        f"engine {engine_status} is gateway-fault under Amendment 1; "
        f"must surface as 502 not {http_exc.status_code}"
    )
    assert http_exc.detail["error"] == "engine_unavailable"
    assert any(
        "gateway_engine_misconfiguration" in rec.message for rec in caplog.records
    )


@pytest.mark.parametrize("engine_status", [404, 405])
def test_engine_wrong_path_maps_to_gateway_502(engine_status, caplog):
    """The 404 row is not hypothetical — mc11-2026-08-02 opened this arc when
    the gateway called `/depreciation/audit` and the engine 404'd. Under a
    digit-based mapper that would have surfaced as "not found" to the
    caller. Fable Amendment 1: it is gateway-fault, surface as 502."""
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": engine_status, "body": "Not Found"},
        engine="depreciation",
        url="http://dep-engine.test/v1/calculators/depreciation/audit/urn:...",
    )
    with caplog.at_level(logging.ERROR, logger="api.lib.engine_error_mapper"):
        http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 502
    assert http_exc.detail["error"] == "engine_unavailable"
    assert any(
        "gateway_engine_misconfiguration" in rec.message for rec in caplog.records
    )


# ============================================================================
# Amendment 1 (rate-limit) — engine 429 → gateway 503 with Retry-After
# ============================================================================


def test_engine_429_maps_to_gateway_503_rate_limited():
    """Engine rate-limiting the gateway is the caller's problem to retry,
    but it is not "engine is broken" — 503 with Retry-After (Amendment 1).

    When the engine did NOT send a Retry-After, the mapper omits
    `retry_after` from the response entirely (Fable mc00 05:21 UTC:
    *"never synthesise a value if it doesn't"* — a fabricated retry
    interval is a claim about capacity we have no basis for). No
    Retry-After response header is set either.
    """
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={
            "status_code": 429,
            "body": '{"detail":"rate limit exceeded"}',
        },
        engine="depreciation",
        url="http://dep-engine.test",
    )
    http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 503
    assert http_exc.detail["error"] == "engine_rate_limited"
    # Fable no-synthesis: retry_after MUST be absent (not None) when the
    # engine sent no Retry-After.
    assert "retry_after" not in http_exc.detail, (
        "Mapper synthesised a retry_after value when engine sent none. "
        "Fable mc00 05:21 UTC: a fabricated retry interval is a claim "
        "about capacity we have no basis for."
    )
    assert http_exc.headers is None or "Retry-After" not in http_exc.headers


def test_engine_429_forwards_retry_after_header_when_present():
    """When PrologClient forwards a Retry-After hint through
    `detail["headers"]`, the mapper surfaces it verbatim on both the
    detail block and the response headers. Pass-through only — no
    normalisation, no synthesis."""
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={
            "status_code": 429,
            "body": '{"detail":"rate limit"}',
            "headers": {"Retry-After": "30"},
        },
        engine="depreciation",
        url="http://dep-engine.test",
    )
    http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 503
    assert http_exc.detail["retry_after"] == "30"
    assert http_exc.headers is not None
    assert http_exc.headers.get("Retry-After") == "30"


# ============================================================================
# Amendment 1 (unmapped 4xx) — unknown engine 4xx → gateway 502 (conservative)
# ============================================================================


def test_unmapped_4xx_defaults_to_gateway_502(caplog):
    """Unknown 4xx is more likely our fault than the caller's under
    Amendment 1. Charity toward the caller."""
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 418, "body": "I'm a teapot"},
        engine="depreciation",
        url="http://dep-engine.test",
    )
    with caplog.at_level(logging.WARNING, logger="api.lib.engine_error_mapper"):
        http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 502
    assert any(
        "gateway_engine_unmapped_4xx" in rec.message for rec in caplog.records
    )


# ============================================================================
# §6 cosmetic — refusal envelope flatten (Fable mc00-2026-09-04 §6 +
# mc01-2026-09-04 08:28 UTC cell-20 correction)
#
# Fable ruled at mc01 08:28 UTC that the hermetic mapper tests were
# structurally the wrong shape: they assert on what the mapper returns
# (`http_exc.detail`), but the wire shows what FastAPI serialises into
# the response body (`{"detail": http_exc.detail}` — FastAPI wraps
# HTTPException(detail=X) unconditionally in {"detail": X}). Those two
# diverged and hermetic tests missed the wire defect. Fix: response-
# level assertions via TestClient live alongside the hermetic ones.
#
# The mapper's flatten rule (mc01 08:28 UTC):
#   * Engine emits `detail` string that is character-for-character equal
#     to `refusal_class` on the pool-asset path (both = the constant
#     REFUSAL_POOL_ASSET_OUT_OF_T6_SCOPE). This is duplication, not
#     nesting. Mapper pops the inner `detail` key.
#   * Engine emits `detail` string that is meaningful content (e.g.
#     unknown_basis path where detail carries the refusal_reason) and
#     NOT a duplicate of `refusal_class`. Mapper preserves it.
# ============================================================================


def test_engine_400_refusal_class_pops_duplicate_inner_detail_hermetic():
    """Hermetic: when engine's refusal body has
    `detail == refusal_class` (the pool-asset shape wire-verified
    against depreciation-engine refusal.py:94), the mapper's return
    value drops the inner `detail` key."""
    refusal_body = json.dumps(
        {
            "refusal_class": "pool_asset_out_of_t6_scope",
            "detail": "pool_asset_out_of_t6_scope",  # DUPLICATE of refusal_class
            "refusal_payload": {"pool_type": "small_business"},
        }
    )
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 400, "body": refusal_body},
        engine="depreciation",
        url="http://dep-engine.test",
    )
    http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 400
    assert http_exc.detail["refusal_class"] == "pool_asset_out_of_t6_scope"
    assert "detail" not in http_exc.detail, (
        f"Duplicate `detail` key not popped; hermetic mapper return "
        f"still carries it. Got: {http_exc.detail!r}"
    )


def test_engine_400_refusal_class_preserves_meaningful_inner_detail_hermetic():
    """Hermetic counter-test: when engine's refusal body's `detail` field
    carries meaningful content that is NOT a duplicate of `refusal_class`
    (the unknown_basis shape at depreciation-engine routes.py:548),
    the mapper preserves it. Fable ruling mc01 08:28 UTC was scoped
    to duplication, not unconditional pop."""
    refusal_body = json.dumps(
        {
            "refusal_class": "unknown_basis",
            "detail": "Basis 'sf_16' is not recognised; expected one of...",
            "refusal_payload": None,
        }
    )
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 400, "body": refusal_body},
        engine="depreciation",
        url="http://dep-engine.test",
    )
    http_exc = map_engine_error_to_http(exc)
    assert http_exc.detail["refusal_class"] == "unknown_basis"
    assert http_exc.detail.get("detail", "").startswith(
        "Basis 'sf_16' is not recognised"
    ), (
        f"Meaningful `detail` content dropped even though it is not a "
        f"duplicate of refusal_class. Fable mc01 08:28 UTC scope was "
        f"drop-when-duplicate. Got: {http_exc.detail!r}"
    )


def test_engine_400_with_refusal_class_flattens_nested_detail():
    """Cell 8's refusal body was `{"detail": {"detail": {...}}}` — nested
    duplication at the public front door. Fable §6: flat. This test
    keeps the pre-mc01 shape (fixture where detail is a distinct
    sentence) so the drop-when-duplicate rule is asserted as
    non-invasive to non-duplicating bodies."""
    refusal_body = json.dumps(
        {
            "refusal_class": "pool_asset_out_of_t6_scope",
            "detail": "Pool assets are individually out of scope",
            "asset_type": "small_business_pool",
        }
    )
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 400, "body": refusal_body},
        engine="depreciation",
        url="http://dep-engine.test",
    )
    http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 400
    assert http_exc.detail["refusal_class"] == "pool_asset_out_of_t6_scope"
    # No `detail.detail` nested refusal_class.
    assert not (
        isinstance(http_exc.detail.get("detail"), dict)
        and "refusal_class" in http_exc.detail["detail"]
    )
    # Non-duplicate `detail` string SHOULD be preserved (Fable mc01
    # 08:28 UTC scope).
    assert http_exc.detail.get("detail") == (
        "Pool assets are individually out of scope"
    )


def test_refusal_class_body_gets_sanitised_too():
    refusal_body = json.dumps(
        {
            "refusal_class": "pool_asset_out_of_t6_scope",
            "detail": "Pool assets are out of scope",
            "numeric_mode": "serving",
        }
    )
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 400, "body": refusal_body},
        engine="depreciation",
        url="http://dep-engine.test",
    )
    http_exc = map_engine_error_to_http(exc)
    assert "numeric_mode" not in http_exc.detail


# ============================================================================
# Engine 5xx / transport — 502 / 504 semantics (Amendment 2 timeout=504)
# ============================================================================


def test_engine_500_maps_to_gateway_502():
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 500, "body": "internal server error"},
        engine="depreciation",
        url="http://dep-engine.test",
    )
    http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 502
    assert http_exc.detail["error"] == "engine_unavailable"


def test_engine_503_maps_to_gateway_502():
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 503, "body": "Service Unavailable"},
        engine="depreciation",
        url="http://dep-engine.test",
    )
    http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 502


def test_engine_timeout_maps_to_504_gateway_timeout():
    """Fable Flag-1 / Amendment 2 correction: engine_timeout = 504, not 503.
    The request was sent, the engine did not respond in time. That is
    textbook 504 Gateway Timeout. Div7A original 504 was right; FBT and
    depreciation historic 503 are corrected UP to 504."""
    exc = PrologEngineUnavailable(
        error_code="engine_timeout",
        detail="read timeout after 30s",
        engine="depreciation",
        url="http://dep-engine.test",
    )
    http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 504, (
        f"Amendment 2: engine_timeout must map to 504 Gateway Timeout; "
        f"got {http_exc.status_code}"
    )
    assert http_exc.detail["error_code"] == "engine_timeout"


def test_engine_unreachable_maps_to_502():
    """Amendment 2 discriminator: engine never answered the connection
    (refused / DNS / not running) = 502, distinct from 504."""
    exc = PrologEngineUnavailable(
        error_code="engine_unreachable",
        detail="ECONNREFUSED",
        engine="depreciation",
        url="http://dep-engine.test",
    )
    http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 502
    assert http_exc.detail["error_code"] == "engine_unreachable"


def test_engine_label_override_preserves_historic_slug():
    exc = PrologEngineUnavailable(
        error_code="engine_unreachable",
        detail="ECONNREFUSED",
        engine="div7a",
        url="http://div7a-engine.test",
    )
    http_exc = map_engine_error_to_http(exc, engine_label="div7a_engine_unavailable")
    assert http_exc.status_code == 502
    assert http_exc.detail["error"] == "div7a_engine_unavailable"


# ============================================================================
# PrologCalculationError mapper
# ============================================================================


def test_calculation_error_maps_to_502():
    exc = PrologCalculationError(
        error="engine_response_missing_field",
        detail={"field": "wdv_at", "numeric_mode": "serving"},
    )
    http_exc = map_calculation_error_to_http(exc)
    assert http_exc.status_code == 502
    assert http_exc.detail["error"] == "engine_response_missing_field"
    assert "numeric_mode" not in http_exc.detail["detail"]
