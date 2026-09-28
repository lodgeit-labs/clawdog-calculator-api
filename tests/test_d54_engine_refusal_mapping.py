"""D54 (Fable [CALC] 2026-09-28): the gateway must not flatten deterministic
engine refusals to 502.

Each test asserts the surfaced status is NOT 502 (except the synthetic unknown
term, which stays 502 but must say `unrecognised_engine_error`).

Scope mirrors the PR: `api/lib/engine_error_mapper.py` classification +
`FBTCarOperatingCostInput` cross-field validator. The FBT `non_cent_boundary`
refusal is reproduced hermetically here from the exact wire shape observed on
2026-09-28 (engine emits it as a serialiser HTTP 500 whose body is a JSON
string) rather than requiring a live engine.
"""
from __future__ import annotations

import json

from pydantic import ValidationError

from api.lib.engine_error_mapper import (
    map_calculation_error_to_http,
    map_engine_error_to_http,
)
from api.prolog_client import PrologCalculationError, PrologEngineUnavailable
from api.schemas.invocation import FBTCarOperatingCostInput

# --- (d1) Asma's payload → 422 naming BOTH fields, never 502 -----------------

def test_asma_payload_rejected_422_naming_both_fields():
    """acquisitionCost + openingDepreciatedValue both present → gateway 422
    at the pydantic tier, before the engine is called. Both fields named in
    their own `loc`. This is the payload that produced the live 502."""
    payload = {
        "businessUsePercentage": 70,
        "formOfFinance": "owned",
        "acquisitionDate": "2022-07-01",
        "openingDepreciatedValue": 22500,
        "acquisitionCost": 40000,
        "deemedTotal": 22500,
    }
    try:
        FBTCarOperatingCostInput(**payload)
        raise AssertionError("expected ValidationError, payload was accepted")
    except ValidationError as exc:
        errs = exc.errors(include_url=False, include_context=False, include_input=False)
        locs = {str(e["loc"][0]) for e in errs if e["loc"]}
        assert "acquisitionCost" in locs
        assert "openingDepreciatedValue" in locs
        assert all(e["type"] == "mutually_exclusive_inputs" for e in errs)


# --- (d2) FBT non_cent_boundary (names a field) → 422, never 502 -------------

def test_fbt_non_cent_boundary_maps_to_422_not_502():
    """The FBT serialiser refuses a non-cent money value with error term
    `non_cent_boundary`, naming the offending field. It arrives as an engine
    HTTP 500 (serialiser fault) whose body is a JSON string. D54: classify by
    term → 422 in FastAPI validation shape, NOT 502."""
    inner = json.dumps({
        "detail": "D12 serialiser rejected a money value not on a cent boundary.",
        "error": "non_cent_boundary",
        "refusal_payload": {
            "field": "gross_taxable_value",
            "reason": "engine_fault_serialiser",
            "supplied": "33.335",
        },
    })
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 500, "body": inner},
        engine="fbt",
        url="http://fbt-engine.test/v1/calculators/fbt/expense-payment",
    )
    http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 422, http_exc.detail
    assert http_exc.status_code != 502
    # FastAPI validation shape: detail = [{loc, msg, type}]
    detail = http_exc.detail
    assert isinstance(detail, list) and detail
    item = detail[0]
    assert item["type"] == "non_cent_boundary"
    assert "gross_taxable_value" in item["loc"]


def test_calculation_error_non_cent_boundary_via_200_body_maps_to_422():
    """The same classification applies to the 200-with-error path
    (`PrologCalculationError`): a term that names a field → 422, not 502."""
    exc = PrologCalculationError(
        error="non_cent_boundary",
        detail={"field": "gross_taxable_value", "supplied": "33.335"},
    )
    http_exc = map_calculation_error_to_http(exc)
    assert http_exc.status_code == 422
    assert http_exc.status_code != 502
    assert http_exc.detail[0]["type"] == "non_cent_boundary"
    assert "gross_taxable_value" in http_exc.detail[0]["loc"]


# --- (d3) Div7A myr_year_beyond_loan_term → 400 refusal_class, engine plain --

def test_div7a_typed_refusal_maps_to_400_engine_not_unavailable():
    """A Div7A typed refusal (refusal_class) arriving as an engine 400 →
    gateway 400, envelope preserved, and the engine label must NOT end in
    `_unavailable` on a 4xx (the suffix is reserved for transport failures)."""
    engine_body = json.dumps({
        "detail": "remaining term n=0 at MYR income year FY2031 ...",
        "refusal_class": "myr_year_beyond_loan_term",
        "refusal_payload": {"remaining_term_years": 0, "loan_fy": 2023, "myr_fy": 2031},
    })
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 400, "body": engine_body},
        engine="div7a",
        url="http://div7a-engine.test/v1/calculators/div7a/at/urn:...",
    )
    http_exc = map_engine_error_to_http(exc, engine_label="div7a_engine_unavailable")
    assert http_exc.status_code == 400
    assert http_exc.status_code != 502
    detail = http_exc.detail
    # refusal envelope preserved (refusal_class survives)
    blob = json.dumps(detail)
    assert "myr_year_beyond_loan_term" in blob
    # engine label must not carry the transport-only _unavailable suffix
    engine_field = detail.get("engine") if isinstance(detail, dict) else None
    if engine_field is not None:
        assert not engine_field.endswith("_unavailable"), engine_field


# --- (d4) synthetic unknown term → 502 unrecognised_engine_error -------------

def test_unknown_engine_term_stays_502_but_named_unrecognised():
    """An unrecognised engine term still maps to 502 (conservative), but the
    body must say `unrecognised_engine_error` and echo the term verbatim."""
    exc = PrologCalculationError(
        error="totally_novel_engine_condition_xyz",
        detail={"some": "context"},
    )
    http_exc = map_calculation_error_to_http(exc)
    assert http_exc.status_code == 502
    assert http_exc.detail["error"] == "unrecognised_engine_error"
    assert http_exc.detail["engine_term"] == "totally_novel_engine_condition_xyz"
