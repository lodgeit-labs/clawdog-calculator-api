"""Wave A route-dispatch contract gate (mut-2026-05-31-mc15).

Asserts the per-URN pydantic dispatch on the generic
``POST /v1/calculators/{calc_uri}/{period_uri}`` route works end-to-end for
each of the 8 Wave A method-atoms:

- urn:sbrm:calculator:fbt:loan
- urn:sbrm:calculator:fbt:debt-waiver
- urn:sbrm:calculator:fbt:expense-payment
- urn:sbrm:calculator:fbt:expense-payment-in-house
- urn:sbrm:calculator:fbt:property
- urn:sbrm:calculator:fbt:property-in-house
- urn:sbrm:calculator:fbt:residual
- urn:sbrm:calculator:fbt:residual-in-house

For each URN we assert:
1. **Valid body → 200** (with engine mocked to return a canonical response).
2. **Invalid body (missing required field) → 422** with structured detail.
3. **Engine unreachable → 502** with structured ``engine_unavailable`` detail.

This is the Lesson #40 production-resolver-shape pattern applied at the
per-URN dispatch boundary: hermetic green here, paired with the post-deploy
``make smoke-prod`` extension for live-wire green.

NB: Wave A std methods don't consume rate-tables; the in-house variants
consume ``in-house-benefit-cap`` (FY2026 = 1000) which IS present in the
vendored production bundle at ``rate_tables/SBRM_RATE_TABLE/fbt/...``. The
existing ``test_production_bundle.py`` gate already asserts that bundle
existence + readability.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

_FBT_PERIOD_URI_RAW = "urn:sbrm:period:fbt:fy2026"
_FBT_PERIOD_URI = quote(_FBT_PERIOD_URI_RAW, safe="")


_WAVE_A_CASES: list[tuple[str, str, dict[str, Any], str]] = [
    # (urn, expected_engine_method, valid_body, required_field_to_drop)
    (
        "urn:sbrm:calculator:fbt:loan",
        "loan_benefit_type_2",
        {
            "fbtBenchmarkInterestAmount": 4310,
            "interestChargedByEmployer": 1000,
            "otherwiseDeductiblePercentage": 50,
        },
        "interestChargedByEmployer",
    ),
    (
        "urn:sbrm:calculator:fbt:debt-waiver",
        "debt_waiver",
        {"amountWaived": 5000, "interestNoLongerCharged": 250},
        "amountWaived",
    ),
    (
        "urn:sbrm:calculator:fbt:expense-payment",
        "expense_payment",
        {
            "expenseValue": 2000,
            "otherwiseDeductiblePercentage": 50,
            "employeeContribution": 200,
        },
        "expenseValue",
    ),
    (
        "urn:sbrm:calculator:fbt:expense-payment-in-house",
        "in_house_expense_payment",
        {
            "expenseValue": 2000,
            "otherwiseDeductiblePercentage": 50,
            "employeeContribution": 200,
            "inhouseBenefitClaimed": 1000,
        },
        "expenseValue",
    ),
    (
        "urn:sbrm:calculator:fbt:property",
        "property",
        {
            "gstInclusiveValue": 1500,
            "otherwiseDeductiblePercentage": 25,
            "employeeContribution": 0,
        },
        "gstInclusiveValue",
    ),
    (
        "urn:sbrm:calculator:fbt:property-in-house",
        "in_house_property",
        {
            "gstInclusiveValue": 1500,
            "otherwiseDeductiblePercentage": 25,
            "employeeContribution": 0,
            "inhouseBenefitClaimed": 1000,
        },
        "gstInclusiveValue",
    ),
    (
        "urn:sbrm:calculator:fbt:residual",
        "residual",
        {
            "gstInclusiveValue": 800,
            "otherwiseDeductiblePercentage": 0,
            "employeeContribution": 0,
        },
        "gstInclusiveValue",
    ),
    (
        "urn:sbrm:calculator:fbt:residual-in-house",
        "in_house_residual",
        {
            "gstInclusiveValue": 800,
            "otherwiseDeductiblePercentage": 0,
            "employeeContribution": 0,
            "inhouseBenefitClaimed": 1000,
        },
        "gstInclusiveValue",
    ),
]


@pytest.fixture
def client() -> TestClient:
    from api.main import app
    return TestClient(app)


def _canonical_engine_response(taxable_value: float = 1234.56) -> dict[str, Any]:
    """Stub engine response shape carrying the load-bearing fields the route
    extracts to build the manifest + advisory blocks."""
    return {
        "taxable_value": taxable_value,
        "gross_taxable_value": taxable_value,
        "employee_contribution": 0,
        "reductions": 0,
        "fbt_type": "Type 2",
        "rate_uris_consumed": [],
        "trace": {"applied_rate_table_uris": []},
    }


@pytest.mark.parametrize("urn,engine_method,valid_body,required_field", _WAVE_A_CASES)
def test_wave_a_route_dispatch_valid_body_returns_200(
    client: TestClient,
    urn: str,
    engine_method: str,
    valid_body: dict[str, Any],
    required_field: str,
) -> None:
    """Per-URN: valid body invokes the engine with the right method-atom."""
    calc_uri_enc = quote(urn, safe="")
    with patch(
        "api.routes.calculators.PrologClient.calculate_fbt",
        new=AsyncMock(return_value=_canonical_engine_response()),
    ) as mock_calc:
        resp = client.post(
            f"/v1/calculators/{calc_uri_enc}/{_FBT_PERIOD_URI}",
            json=valid_body,
        )
    assert resp.status_code == 200, f"{urn}: expected 200, got {resp.status_code}: {resp.text[:300]}"
    # The engine should have been called with the per-URN benefit_category + method
    mock_calc.assert_called_once()
    sent_payload = mock_calc.call_args.args[0]
    assert sent_payload.get("method") == engine_method, (
        f"{urn}: engine called with method={sent_payload.get('method')!r}, "
        f"expected {engine_method!r}"
    )


@pytest.mark.parametrize("urn,engine_method,valid_body,required_field", _WAVE_A_CASES)
def test_wave_a_route_dispatch_invalid_body_returns_422(
    client: TestClient,
    urn: str,
    engine_method: str,
    valid_body: dict[str, Any],
    required_field: str,
) -> None:
    """Per-URN: dropping a required field returns 422 (not 500)."""
    calc_uri_enc = quote(urn, safe="")
    bad_body = {k: v for k, v in valid_body.items() if k != required_field}
    with patch(
        "api.routes.calculators.PrologClient.calculate_fbt",
        new=AsyncMock(return_value=_canonical_engine_response()),
    ):
        resp = client.post(
            f"/v1/calculators/{calc_uri_enc}/{_FBT_PERIOD_URI}",
            json=bad_body,
        )
    assert resp.status_code == 422, (
        f"{urn}: expected 422 on missing {required_field!r}, got "
        f"{resp.status_code}: {resp.text[:300]}"
    )


@pytest.mark.parametrize("urn,engine_method,valid_body,required_field", _WAVE_A_CASES)
def test_wave_a_route_dispatch_engine_unreachable_returns_502(
    client: TestClient,
    urn: str,
    engine_method: str,
    valid_body: dict[str, Any],
    required_field: str,
) -> None:
    """Per-URN: engine unreachable raises PrologEngineUnavailable → 502."""
    from api.prolog_client import PrologEngineUnavailable

    calc_uri_enc = quote(urn, safe="")
    with patch(
        "api.routes.calculators.PrologClient.calculate_fbt",
        new=AsyncMock(side_effect=PrologEngineUnavailable(
            engine="fbt",
            error_code="engine_unreachable",
            detail="connection refused",
        )),
    ):
        resp = client.post(
            f"/v1/calculators/{calc_uri_enc}/{_FBT_PERIOD_URI}",
            json=valid_body,
        )
    assert resp.status_code == 502, (
        f"{urn}: expected 502 on engine unreachable, got "
        f"{resp.status_code}: {resp.text[:300]}"
    )
    body = resp.json()
    assert body["detail"]["error"] == "engine_unavailable"
    assert body["detail"]["error_code"] == "engine_unreachable"
    assert body["detail"]["engine"] == "fbt"
