"""D73 (Fable [CALC] 2026-11-08): gateway-wide uniform refusal + 422 contract.

One parametrised test asserts the uniform 400 refusal envelope for a refusal
from EACH module (fbt / div7a / depreciation / hp), and a second asserts the
422 `loc` convention is shared across modules. The engine bodies are the real
wire shapes captured in step 0 of the D73 dispatch (the FBT out-of-cohort body
is the production capture reused from tests/test_d62_cohort_refusal_mapping.py;
the div7a / depreciation 400 bodies are the engine refusal envelopes; the HP
refusal is driven through the live route against its own pure-Decimal engine).

Target 400 contract (every module):

    {"detail": {"refusal_class": "...", "refusal_payload": {...},
                "engine": "<module>", "message": "..."}}

  * refusal_class is ALWAYS at the top level (parsed out of any stringified
    engine body).
  * engine is the module name from _engine_name_for (fbt/div7a/depreciation/hp),
    never the "_unavailable" transport label.
  * legacy keys (error / field / engine_detail / detail) MAY remain alongside
    for backward compatibility (deprecation note in the D73 report); the test
    asserts the uniform keys are present, not that the legacy keys are absent.

Target 422 contract (every module): the FastAPI-native pydantic convention —
`loc` is a list whose first element is "body" — which is what depreciation, HP,
and div7a native pydantic 422s already emit, and what FBT (via the generic
route's sub-context validation) and the mapper's synthetic engine-422s now emit
too after D73.
"""
from __future__ import annotations

import json
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.lib.engine_error_mapper import map_engine_error_to_http
from api.main import app
from api.prolog_client import PrologEngineUnavailable


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Real engine refusal bodies captured in step 0.
# ---------------------------------------------------------------------------

# (a) Div 7A — MYR year beyond loan term; engine HTTP 400 + refusal_class.
_DIV7A_400_BODY = json.dumps(
    {
        "refusal_class": "myr_year_beyond_loan_term",
        "refusal_payload": {"remaining_term_years": 0, "loan_fy": 2023, "myr_fy": 2031},
        "detail": "remaining term n=0 at MYR income year FY2031 is beyond loan term",
    }
)

# (a') Div 7A — Argon's verbatim captured body (D73 follow-up 2026-11-08): the
# engine re-returns an ALREADY-gateway-wrapped body whose real refusal_class is
# nested inside a stringified `engine_detail`. The uniform contract must still
# surface refusal_class at the top level and engine as the module name.
# Argon's exact wire body:
#   {"detail":{"error":"engine_bad_request","engine":"div7a_engine",
#     "status_code":400,"engine_detail":"{\"detail\":\"…\",
#     \"refusal_class\":\"myr_year_not_after_loan_year\",
#     \"refusal_payload\":{…}}"}}
# The inner object below is reproduced verbatim as the engine's stringified
# engine_detail; the gateway receives it as the engine's 400 body.
_ARGON_DIV7A_INNER = json.dumps(
    {
        "detail": "MYR income year is not after the loan's making year",
        "refusal_class": "myr_year_not_after_loan_year",
        "refusal_payload": {"loan_making_fy": 2024, "myr_fy": 2024},
    }
)
_ARGON_DIV7A_400_BODY = json.dumps(
    {
        "error": "engine_bad_request",
        "engine": "div7a_engine",
        "status_code": 400,
        "engine_detail": _ARGON_DIV7A_INNER,
    }
)

# (b) Depreciation — pool asset out of T6 scope; engine emits detail==refusal_class.
_DEP_400_BODY = json.dumps(
    {
        "detail": "pool_asset_out_of_t6_scope",
        "refusal_class": "pool_asset_out_of_t6_scope",
        "refusal_payload": {"asset_class": "pool"},
    }
)

# (d) FBT — out-of-cohort, production-captured double-wrapped body (2026-09-28):
# the engine wraps fbt_year_outside_cohort inside calculation_failed and carries
# the real term as text (reused from test_d62_cohort_refusal_mapping.py).
_FBT_500_WRAPPED_BODY = (
    '{"error":"unrecognised_engine_error","engine_term":"calculation_failed",'
    '"engine_detail":"Unknown error term: calculation_failed(error('
    "fbt_year_outside_cohort(fy(fy2006),cohort_period("
    'fbt_year(fy2022),fbt_year(fy2030))),_G1))"}'
)


def _engine_exc(status_code: int, body: str, engine: str) -> PrologEngineUnavailable:
    return PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": status_code, "body": body},
        engine=engine,
        url=f"http://{engine}-engine.test/v1",
    )


# (refusal_class, expected_engine, mapper call → HTTPException)
_MAPPER_400_CASES = [
    pytest.param(
        "div7a",
        "myr_year_beyond_loan_term",
        "div7a",
        lambda: map_engine_error_to_http(
            _engine_exc(400, _DIV7A_400_BODY, "div7a"),
            engine_label="div7a_engine_unavailable",
            engine_name="div7a",
        ),
        id="div7a-myr-beyond-loan-term",
    ),
    pytest.param(
        "div7a",
        "myr_year_not_after_loan_year",
        "div7a",
        lambda: map_engine_error_to_http(
            _engine_exc(400, _ARGON_DIV7A_400_BODY, "div7a"),
            engine_label="div7a_engine_unavailable",
            engine_name="div7a",
        ),
        id="div7a-argon-verbatim-nested-refusal-class",
    ),
    pytest.param(
        "depreciation",
        "pool_asset_out_of_t6_scope",
        "depreciation",
        lambda: map_engine_error_to_http(
            _engine_exc(400, _DEP_400_BODY, "depreciation"),
            engine_name="depreciation",
        ),
        id="depreciation-pool-asset-out-of-t6-scope",
    ),
    pytest.param(
        "fbt",
        "fbt_year_outside_cohort",
        "fbt",
        lambda: map_engine_error_to_http(
            _engine_exc(500, _FBT_500_WRAPPED_BODY, "fbt"),
            engine_name="fbt",
        ),
        id="fbt-year-outside-cohort",
    ),
]


@pytest.mark.parametrize("module,refusal_class,engine,call", _MAPPER_400_CASES)
def test_uniform_400_refusal_envelope_per_module(
    module: str, refusal_class: str, engine: str, call
) -> None:
    """Every module's 400 refusal carries the uniform envelope:
    refusal_class (top-level) + refusal_payload + engine (module name) + message.
    """
    http_exc = call()
    assert http_exc.status_code == 400, http_exc.detail
    detail = http_exc.detail
    assert isinstance(detail, dict), detail
    # refusal_class is ALWAYS at the top level.
    assert detail.get("refusal_class") == refusal_class
    # engine names the module, never the "_unavailable" transport label.
    assert detail.get("engine") == engine
    assert not str(detail.get("engine")).endswith("_unavailable")
    # refusal_payload + message are present.
    assert "refusal_payload" in detail
    assert isinstance(detail["refusal_payload"], dict)
    assert isinstance(detail.get("message"), str) and detail["message"]


def test_uniform_400_refusal_envelope_hp_via_live_route(client: TestClient) -> None:
    """(c) HP: non-monthly frequency → 400 uniform envelope via the live route.

    HP builds its refusal in the route handler (not the mapper). The engine is
    the pure-Decimal HP schedule engine, driven here through the mounted app.
    Legacy keys (error / field / detail) remain; uniform keys are asserted.
    """
    hp_body = {
        "amount_financed": "10000.00",
        "annual_rate_pct": "12.0",
        "term_regular_instalments": 12,
        "instalment": "900.00",
        "timing": "in_arrears",
        "frequency": "weekly",  # non-monthly → unsupported_frequency refusal
        "begin_date": "2024-01-01",
        "contract_form": "hire_purchase",
    }
    resp = client.post("/v1/calculators/hp/schedule", json=hp_body)
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["refusal_class"] == "unsupported_frequency"
    assert detail["engine"] == "hp"
    assert not str(detail["engine"]).endswith("_unavailable")
    assert isinstance(detail["refusal_payload"], dict)
    assert isinstance(detail["message"], str) and detail["message"]
    # Legacy keys kept for compatibility (deprecation note in D73 report).
    assert detail["error"] == "unsupported_frequency"
    assert detail["field"] == "frequency"


def test_argon_verbatim_div7a_body_flattens_to_top_level_refusal_class() -> None:
    """D73 follow-up (Fable [CALC] 2026-11-08): Argon's verbatim captured Div 7A
    body — where refusal_class is buried inside a stringified `engine_detail`
    and `engine` is the historic `div7a_engine` label — MUST flatten to the
    uniform envelope with refusal_class at the top level and engine="div7a".
    """
    http_exc = map_engine_error_to_http(
        _engine_exc(400, _ARGON_DIV7A_400_BODY, "div7a"),
        engine_label="div7a_engine_unavailable",
        engine_name="div7a",
    )
    assert http_exc.status_code == 400, http_exc.detail
    detail = http_exc.detail
    assert isinstance(detail, dict)
    # The two assertions Fable named explicitly.
    assert detail["refusal_class"] == "myr_year_not_after_loan_year"
    assert detail["engine"] == "div7a"
    # engine must not be the historic "div7a_engine" / "_unavailable" label.
    assert detail["engine"] != "div7a_engine"
    assert not str(detail["engine"]).endswith("_unavailable")
    # refusal_payload is recovered from the nested body.
    assert detail["refusal_payload"] == {"loan_making_fy": 2024, "myr_fy": 2024}


# ---------------------------------------------------------------------------
# 422 loc convention: first element is "body" across every module.
# ---------------------------------------------------------------------------

_FBT_CAR_OPCOST = "urn:sbrm:calculator:fbt:car-operating-cost"
_FBT_FY2026 = "urn:sbrm:period:fbt:fy2026"
_DEP_AT_FY2026 = "urn:sbrm:period:depreciation:fy2026"


def _loc_prefixes(detail) -> list:
    assert isinstance(detail, list) and detail, detail
    return [e.get("loc", [None])[0] for e in detail]


@pytest.mark.parametrize(
    "method,url,body",
    [
        pytest.param(
            "generic-fbt",
            f"/v1/calculators/{quote(_FBT_CAR_OPCOST, safe='')}/"
            f"{quote(_FBT_FY2026, safe='')}",
            {},
            id="fbt-generic-route-422",
        ),
        pytest.param(
            "native-depreciation",
            f"/v1/calculators/depreciation/at/{quote(_DEP_AT_FY2026, safe='')}",
            {},
            id="depreciation-native-422",
        ),
        pytest.param(
            "native-hp",
            "/v1/calculators/hp/schedule",
            {},
            id="hp-native-422",
        ),
    ],
)
def test_uniform_422_loc_convention_body_prefixed(
    client: TestClient, method: str, url: str, body: dict
) -> None:
    """Every module's 422 `loc` starts with "body" — the FastAPI-native pydantic
    convention that depreciation/div7a/HP native routes already emit, and that
    the FBT generic-route sub-context validation now emits too after D73.
    """
    resp = client.post(url, json=body)
    assert resp.status_code == 422, resp.text
    prefixes = _loc_prefixes(resp.json()["detail"])
    assert prefixes, resp.text
    assert all(p == "body" for p in prefixes), (method, resp.json()["detail"])


def test_mapper_synthetic_422_loc_is_body_prefixed() -> None:
    """The mapper's synthetic engine-fault 422 (non_cent_boundary on a request
    field) also prefixes "body", matching the native-pydantic convention.
    """
    inner = json.dumps(
        {
            "refusal_class": "non_cent_boundary",
            "refusal_payload": {
                "field": "employee_contribution",  # resolves to alias
                "reason": "employeeContribution must be cent-quantised",
            },
            "reason": "engine_fault_serialiser",
        }
    )
    http_exc = map_engine_error_to_http(
        _engine_exc(500, inner, "fbt"),
        engine_name="fbt",
    )
    assert http_exc.status_code == 422, http_exc.detail
    detail = http_exc.detail
    assert isinstance(detail, list) and detail
    assert detail[0]["loc"][0] == "body"
