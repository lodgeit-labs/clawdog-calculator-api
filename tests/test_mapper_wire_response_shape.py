"""Mapper wire-response shape tests — assert what FastAPI serialises,
not what the mapper returns.

**Fable mc01-2026-09-04 08:28 UTC (verbatim):**

  "Your hermetic mapper tests assert on what the mapper returns; the
   wire shows what FastAPI serialises. Those diverged and nothing
   caught it. Add an assertion at the response level, through
   TestClient, not at the mapper's return value — otherwise the same
   gap swallows the next envelope change."

Anchor: cell 20 (§6 flatten) reported as shipped in commit `a8c965f`;
Fable's post-merge probe against the deployed gateway 2026-09-04 08:27
UTC found the wire response was:

    HTTP 400
    {"detail": {"detail": "pool_asset_out_of_t6_scope",
                "refusal_class": "pool_asset_out_of_t6_scope",
                "refusal_payload": {...}}}

Character-for-character identical to the pre-#33 shape. The hermetic
mapper tests passed because they asserted on `http_exc.detail`
(structural: the arg passed to HTTPException) rather than on the
JSON-serialised response body (structural: what FastAPI writes to the
wire). FastAPI wraps `HTTPException(detail=X)` unconditionally in
`{"detail": X}`, so if X carries its own `detail` key, the response has
`detail.detail`.

This file asserts against the wire-serialised response, using
`TestClient(app).post(...)` — the same substrate that the deployed
gateway exposes to a caller. Every assertion is on the parsed JSON of
the response body, not on any internal mapper structure.

**Design covenant**: any future flattening / sanitisation / envelope
change in the mapper adds a matching test HERE, not just at the
hermetic layer. Two boundaries: one for structural correctness (the
mapper), one for wire correctness (FastAPI's serialisation of what the
mapper produced). Nothing in this file uses `map_engine_error_to_http`
directly.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.prolog_client import PrologEngineUnavailable

DEP_AT_URL = (
    f"/v1/calculators/depreciation/at/"
    f"{quote('urn:sbrm:period:depreciation:unscoped', safe='')}"
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _valid_dep_at_payload_with_pool() -> dict:
    """Payload that reaches the engine and would trigger a pool-refusal
    (the wire scenario Fable exercised in cell 20). `pool_type` is
    accepted by the gateway schema per F2-β mc11-2026-08-31 ratification;
    the engine's own D2 fold refuses it with the typed refusal."""
    return {
        "basis": "accounting",
        "asset": {
            "cost": "5000.00",
            "acquisition_date": "2022-07-01",
            "accounting_useful_life_years": 10,
            "accounting_method": "prime_cost",
            "pool_type": "small_business",
        },
        "at_date": "2025-06-30",
    }


def _mock_engine_refusal(
    refusal_class: str,
    detail_string: str,
    refusal_payload: dict | None = None,
) -> PrologEngineUnavailable:
    """Build a PrologEngineUnavailable that mirrors the engine's HTTP 400
    typed-refusal envelope shape."""
    return PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={
            "status_code": 400,
            "body": json.dumps(
                {
                    "detail": detail_string,
                    "refusal_class": refusal_class,
                    "refusal_payload": refusal_payload,
                }
            ),
        },
        engine="depreciation",
        url="http://dep-engine.test",
    )


# ============================================================================
# Cell 20 (Fable mc01 08:28 UTC) — pool-asset refusal, wire response body
# ============================================================================


def test_wire_pool_asset_refusal_body_carries_no_detail_detail_nesting(
    client: TestClient,
) -> None:
    """Cell 20 replay against the mounted app. Wire body must NOT contain
    `detail.detail` — the flatten cosmetic must reach the response, not
    just the mapper's return value.

    This is the assertion that catches what the hermetic mapper tests
    missed at #33 ship.
    """
    engine_refusal = _mock_engine_refusal(
        refusal_class="pool_asset_out_of_t6_scope",
        # ENGINE emits this string, which is character-for-character
        # equal to refusal_class on the pool-asset path
        # (REFUSAL_POOL_ASSET_OUT_OF_T6_SCOPE == "pool_asset_out_of_t6_scope"
        # in depreciation-engine/refusal.py:94; wire-verified 2026-09-04).
        detail_string="pool_asset_out_of_t6_scope",
        refusal_payload={"pool_type": "small_business"},
    )
    with patch(
        "api.routes.calculators.PrologClient.depreciation_at",
        new_callable=AsyncMock,
        side_effect=engine_refusal,
    ):
        resp = client.post(
            DEP_AT_URL,
            json=_valid_dep_at_payload_with_pool(),
        )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    # FastAPI wraps HTTPException(detail=X) in {"detail": X}, so we expect
    # one level of `detail` at the top.
    assert "detail" in body
    inner = body["detail"]
    assert isinstance(inner, dict), (
        f"Wire response's top-level detail must be a dict (the refusal "
        f"envelope). Got: {type(inner).__name__}: {inner!r}"
    )
    # The refusal envelope must NOT itself contain a `detail` key that
    # duplicates refusal_class.
    assert "detail" not in inner, (
        f"Wire response STILL has detail.detail. Cell 20 defect. "
        f"Fable's 08:28 UTC probe found this exact shape; a hermetic "
        f"assertion at the mapper's return did NOT catch it because "
        f"FastAPI wraps HTTPException(detail=X) unconditionally in "
        f'{{"detail": X}}. Wire body: {body!r}'
    )
    # And the typed field the caller acts on must be present + correct.
    assert inner["refusal_class"] == "pool_asset_out_of_t6_scope"
    assert inner["refusal_payload"] == {"pool_type": "small_business"}


def test_wire_refusal_preserves_meaningful_inner_detail(
    client: TestClient,
) -> None:
    """Counter-test: when the engine's refusal `detail` string is
    meaningful content (unknown_basis path where detail carries the
    refusal_reason — wire-referenced at
    depreciation-engine/routes.py:548), the wire response MUST preserve
    the string. Fable ruling mc01 08:28 UTC scope was drop-when-duplicate,
    not unconditional pop."""
    engine_refusal = _mock_engine_refusal(
        refusal_class="unknown_basis",
        detail_string="Basis 'sf_16' is not recognised; expected one of...",
        refusal_payload=None,
    )
    with patch(
        "api.routes.calculators.PrologClient.depreciation_at",
        new_callable=AsyncMock,
        side_effect=engine_refusal,
    ):
        resp = client.post(
            DEP_AT_URL,
            json=_valid_dep_at_payload_with_pool(),
        )
    assert resp.status_code == 400
    body = resp.json()
    inner = body["detail"]
    assert inner["refusal_class"] == "unknown_basis"
    # The distinct detail sentence must survive.
    assert inner.get("detail", "").startswith("Basis 'sf_16' is not recognised"), (
        f"Non-duplicate `detail` was dropped from the wire response. "
        f"Fable ruling mc01 08:28 UTC was drop-when-duplicate. Got: {inner!r}"
    )


# ============================================================================
# Adjacent wire-response envelope assertions (guardrail for future
# mapper envelope changes — same discipline, different fixtures).
# ============================================================================


def test_wire_422_engine_validation_error_shape(client: TestClient) -> None:
    """Engine 422 → gateway 422 wire body carries `error` + `engine` +
    `status_code` + `engine_detail` at the FastAPI-wrapped-detail level.
    Pins the mapper's engine_validation_error envelope on the wire."""
    engine_422 = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={
            "status_code": 422,
            "body": json.dumps(
                {
                    "error": "validation",
                    "field": "asset.accounting_useful_life_years",
                    "detail": (
                        "basis='accounting' requires "
                        "'asset.accounting_useful_life_years'"
                    ),
                }
            ),
        },
        engine="depreciation",
        url="http://dep-engine.test",
    )
    with patch(
        "api.routes.calculators.PrologClient.depreciation_at",
        new_callable=AsyncMock,
        side_effect=engine_422,
    ):
        resp = client.post(
            DEP_AT_URL,
            json=_valid_dep_at_payload_with_pool(),
        )
    assert resp.status_code == 422
    body = resp.json()
    inner = body["detail"]
    assert inner["error"] == "engine_validation_error"
    assert inner["engine"] == "depreciation"
    assert inner["status_code"] == 422
    assert "engine_detail" in inner


def test_wire_502_engine_5xx_shape(client: TestClient) -> None:
    """Engine 5xx → gateway 502 wire body carries `error` = engine_unavailable
    at the FastAPI-wrapped-detail level. Pins the mapper's 5xx envelope
    on the wire."""
    engine_500 = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 500, "body": "internal server error"},
        engine="depreciation",
        url="http://dep-engine.test",
    )
    with patch(
        "api.routes.calculators.PrologClient.depreciation_at",
        new_callable=AsyncMock,
        side_effect=engine_500,
    ):
        resp = client.post(
            DEP_AT_URL,
            json=_valid_dep_at_payload_with_pool(),
        )
    assert resp.status_code == 502
    body = resp.json()
    inner = body["detail"]
    assert inner["error"] == "engine_unavailable"


def test_wire_504_engine_timeout_shape(client: TestClient) -> None:
    """engine_timeout → 504 Gateway Timeout on the wire (Fable Amendment 2
    correction of prior 503 ruling)."""
    engine_timeout = PrologEngineUnavailable(
        error_code="engine_timeout",
        detail="read timeout after 30s",
        engine="depreciation",
        url="http://dep-engine.test",
    )
    with patch(
        "api.routes.calculators.PrologClient.depreciation_at",
        new_callable=AsyncMock,
        side_effect=engine_timeout,
    ):
        resp = client.post(
            DEP_AT_URL,
            json=_valid_dep_at_payload_with_pool(),
        )
    assert resp.status_code == 504
    body = resp.json()
    assert body["detail"]["error_code"] == "engine_timeout"
