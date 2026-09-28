"""D56 (Fable [CALC] 2026-09-28): money inputs are validated for cent scale at
parse time, before any engine call.

Every case asserts the surfaced status is NOT 502: a sub-cent money value is a
422 `money_not_cent_quantised` from the schema (the engine is never called),
and cent-scale values (number or decimal string, trailing zeros included) pass
schema validation and reach the (mocked) engine.
"""
from __future__ import annotations

from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.main import app

FBT_PERIOD = "urn:sbrm:period:fbt:fy2026"
DIV7A_PERIOD = "urn:sbrm:period:div7a:fy2026"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _fbt_url(calc_uri: str) -> str:
    return f"/v1/calculators/{quote(calc_uri, safe='')}/{quote(FBT_PERIOD, safe='')}"


def _div7a_url() -> str:
    return f"/v1/calculators/div7a/at/{DIV7A_PERIOD}"


# The six D55 calculators that returned 200 on 33.335 — minimal otherwise-valid
# body with the money field set to a sub-cent probe. Field names verified
# against the committed OpenAPI.
_SUB_CENT_CASES = [
    (
        "urn:sbrm:calculator:fbt:car-operating-cost",
        "acquisitionCost",
        {
            "businessUsePercentage": 70,
            "formOfFinance": "owned",
            "acquisitionDate": "2022-07-01",
            "acquisitionCost": 33.335,
        },
    ),
    (
        "urn:sbrm:calculator:fbt:lafha",
        "accommodationPerWeek",
        {"weeksLivedAway": 10, "accommodationPerWeek": 33.335, "mealsPerWeek": 100},
    ),
    (
        "urn:sbrm:calculator:fbt:car-parking-actual",
        "valuationMethodRate",
        {"spacesProvided": 1, "valuationMethodRate": 33.335},
    ),
    (
        "urn:sbrm:calculator:fbt:car-parking-statutory-228",
        "valuationMethodRate",
        {"daysCarParkingAvailable": 200, "valuationMethodRate": 33.335},
    ),
    (
        "urn:sbrm:calculator:fbt:car-parking-register-12wk",
        "valuationMethodRate",
        {
            "benefitsInPeriod": 5,
            "valuationMethodRate": 33.335,
            "daysSpaceAvailable": 200,
        },
    ),
    (
        "urn:sbrm:calculator:fbt:car-statutory-formula",
        "baseValue",
        {"baseValue": 33.335, "daysAvailable": 365},
    ),
]


@pytest.mark.parametrize(
    "calc_uri,alias,body",
    _SUB_CENT_CASES,
    ids=[c[0].split(":")[-1] + ":" + c[1] for c in _SUB_CENT_CASES],
)
def test_sub_cent_money_refused_422_naming_alias(client, calc_uri, alias, body):
    resp = client.post(_fbt_url(calc_uri), json=body)
    assert resp.status_code != 502, resp.text
    assert resp.status_code == 422, resp.text
    errors = resp.json()["detail"]
    matching = [e for e in errors if e.get("type") == "money_not_cent_quantised"]
    assert matching, errors
    assert any(alias in [str(x) for x in e.get("loc", [])] for e in matching), errors
    assert any(alias in e.get("msg", "") for e in matching), errors


def test_expense_payment_sub_cent_refused_before_engine(client):
    """expense-payment employeeContribution: 33.335 → 422 from the schema; the
    engine is never called.

    The refusal is a FastAPI request-validation error: pydantic parses (and
    rejects) the body BEFORE the route function body runs, so no engine call is
    reachable. We assert this structurally — the body is the pure validation
    error shape (a list of {loc, msg, type} items), never an engine envelope
    (which would be a dict with `error`/`engine`/`engine_detail`).
    """
    resp = client.post(
        _fbt_url("urn:sbrm:calculator:fbt:expense-payment"),
        json={
            "expenseValue": 100,
            "otherwiseDeductiblePercentage": 0,
            "fbtType": "Type 1",
            "employeeContribution": 33.335,
        },
    )
    assert resp.status_code == 422, resp.text
    assert resp.status_code != 502
    errors = resp.json()["detail"]
    # Pure request-validation shape proves parse-time refusal (no engine call).
    assert isinstance(errors, list), errors
    assert any(
        e.get("type") == "money_not_cent_quantised"
        and "employeeContribution" in [str(x) for x in e.get("loc", [])]
        for e in errors
    ), errors


def test_div7a_amalgamated_base_sub_cent_refused_422(client):
    """div7a amalgamated_base: 80000.005 → 422 money_not_cent_quantised."""
    resp = client.post(
        _div7a_url(),
        json={
            "amalgamated_base": 80000.005,
            "loan_term_years": 7,
            "loan_origination_date": "2022-07-01",
            "income_year_start_date": "2023-07-01",
            "repayments": [],
        },
    )
    assert resp.status_code != 502, resp.text
    assert resp.status_code == 422, resp.text
    errors = resp.json()["detail"]
    assert any(
        e.get("type") == "money_not_cent_quantised"
        and "amalgamated_base" in [str(x) for x in e.get("loc", [])]
        for e in errors
    ), errors


# --- cent-scale values pass the schema (reach the mocked engine) -------------

_EXPENSE_URI = "urn:sbrm:calculator:fbt:expense-payment"


def _expense_body(employee_contribution):
    return {
        "expenseValue": 100,
        "otherwiseDeductiblePercentage": 0,
        "fbtType": "Type 1",
        "employeeContribution": employee_contribution,
    }


def test_cent_scale_string_equals_number(fastapi_test_client):
    """A decimal string "33.33" is accepted and produces the same result as the
    number 33.33 (both reach the mocked engine and return its fixture)."""
    url = _fbt_url(_EXPENSE_URI)
    r_str = fastapi_test_client.post(url, json=_expense_body("33.33"))
    r_num = fastapi_test_client.post(url, json=_expense_body(33.33))
    assert r_str.status_code == 200, r_str.text
    assert r_num.status_code == 200, r_num.text
    assert r_str.json() == r_num.json()


def test_trailing_zeros_are_cent_scale(fastapi_test_client):
    """33.3300 has trailing zeros only → accepted (reaches the engine)."""
    resp = fastapi_test_client.post(
        _fbt_url(_EXPENSE_URI), json=_expense_body(33.3300)
    )
    assert resp.status_code == 200, resp.text
