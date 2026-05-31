"""Wave A + Wave B route-dispatch contract gate (mut-2026-05-31-mc15 + mc17).

Asserts the per-URN pydantic dispatch on the generic
``POST /v1/calculators/{calc_uri}/{period_uri}`` route works end-to-end for
each Wave A + Wave B method-atom.

Wave A (mut-2026-05-31-mc15; Phase 2a–2e originals):
- urn:sbrm:calculator:fbt:loan
- urn:sbrm:calculator:fbt:debt-waiver
- urn:sbrm:calculator:fbt:expense-payment
- urn:sbrm:calculator:fbt:expense-payment-in-house
- urn:sbrm:calculator:fbt:property
- urn:sbrm:calculator:fbt:property-in-house
- urn:sbrm:calculator:fbt:residual
- urn:sbrm:calculator:fbt:residual-in-house

Wave B (mut-2026-05-31-mc17; Phase 2f–2i single-method calcs):
- urn:sbrm:calculator:fbt:housing
- urn:sbrm:calculator:fbt:lafha
- urn:sbrm:calculator:fbt:board
- urn:sbrm:calculator:fbt:tebe

For each URN we assert:
1. **Valid body → 200** (with engine mocked to return a canonical response).
2. **Invalid body (missing required field) → 422** with structured detail.
3. **Engine unreachable → 502** with structured ``engine_unavailable`` detail.

This is the Lesson #40 production-resolver-shape pattern applied at the
per-URN dispatch boundary: hermetic green here, paired with the post-deploy
``make smoke-prod`` extension for live-wire green.

NB: Wave A std methods + Wave B Housing/LAFHA/Board/TEBE don't consume
rate-tables at the engine layer (Wave A in-house variants consume
``in-house-benefit-cap`` which IS present in the vendored production bundle).
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
    # --- Wave B (mut-2026-05-31-mc17; Phase 2f–2i single-method calcs) ---
    (
        "urn:sbrm:calculator:fbt:housing",
        "housing_non_remote",
        {
            "housingBenefitValue": 12000,
            "indexationFactor": 1.05,
            "recipientRent": 2000,
        },
        "housingBenefitValue",
    ),
    (
        "urn:sbrm:calculator:fbt:lafha",
        "lafha_std",
        {
            "weeksLivedAway": 5,
            "accommodationPerWeek": 220,
            "mealsPerWeek": 80,
            "exemptAccommodationComponent": 500,
            "exemptFoodComponent": 100,
        },
        "weeksLivedAway",
    ),
    (
        "urn:sbrm:calculator:fbt:board",
        "board_std",
        {
            "membersUnderTwelve": 3,
            "under12MealsPerChild": 0,
            "membersOverTwelve": 60,
            "over12MealsPerChild": 45,
            "over12EmployeeContributions": 100,
        },
        # All Board fields are optional (default 0); use ``__extra_unknown__``
        # which is rejected by ``extra='forbid'`` to trigger 422.
        "__extra_unknown__",
    ),
    (
        "urn:sbrm:calculator:fbt:tebe",
        "tebe_std",
        {
            "salaryPackagedMealEfle": 5000,
            "recreation": 1500,
        },
        "salaryPackagedMealEfle",
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
    """Per-URN: invalid body returns 422 (not 500).

    For URNs with at least one required field, we drop that field. For
    URNs whose schema is entirely optional fields (e.g. Board where all
    inputs default to 0), we inject an unknown field which is rejected by
    ``model_config = ConfigDict(extra='forbid')``.
    """
    calc_uri_enc = quote(urn, safe="")
    if required_field == "__extra_unknown__":
        # Inject an unknown field rejected by extra='forbid'.
        bad_body = {**valid_body, "unknownExtraField": 999}
    else:
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
        f"{urn}: expected 422 on invalid body shape ({required_field!r}), got "
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
