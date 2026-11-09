"""D79 (Fable, 2026-11-09): inhouseBenefitClaimed belongs to the in-house FBT
variants only.

Defect (verified live through the gateway 2026-11-09): the three standard
(non-in-house) FBT calculators accepted ``inhouseBenefitClaimed`` because they
inherited it from the shared bases ``_ExpensePaymentBaseInput``,
``_PropertyBaseInput`` and ``_ResidualBaseInput``. On expense-payment the s.62
in-house reduction was wrongly applied to a standard benefit (taxable_value
800.00 -> 0.00); on property/residual the field was accepted and silently
ignored, breaking "refuse, don't guess".

Fix (gateway only): the field moved off the shared bases onto the three
in-house input models (``FBTExpensePaymentInHouseInput``,
``FBTPropertyInHouseInput``, ``FBTResidualInHouseInput``). The standard models
keep ``extra="forbid"``, so sending the field to a standard calculator now
returns 422 ``extra_forbidden`` at loc ``["body","inhouseBenefitClaimed"]``.

This test asserts:
  (a) each of the 3 standard calculators rejects the field (422 extra_forbidden
      at that loc);
  (b) each of the 3 in-house calculators still accepts the field and forwards
      it to the engine as snake_case ``inhouse_benefit_claimed``;
  (c) the standard expense-payment request WITHOUT the field forwards the same
      engine body as before (no inhouse_benefit_claimed key).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.main import app

_FBT_PERIOD = "urn:sbrm:period:fbt:fy2026"


def _url(calc_uri: str) -> str:
    return f"/v1/calculators/{quote(calc_uri, safe='')}/{quote(_FBT_PERIOD, safe='')}"


def _canonical_engine_response(taxable_value: float = 1234.56) -> dict[str, Any]:
    """Minimal post-D12 engine wire shape carrying the fields the route
    extracts to build manifest + advisory. Money as 2dp strings."""
    grossed_up = round(taxable_value * 1.8868, 2)
    fbt_pay = round(grossed_up * 0.47, 2)

    def m(v: float) -> str:
        return f"{v:.2f}"

    return {
        "taxable_value": m(taxable_value),
        "gross_taxable_value": m(taxable_value),
        "employee_contribution": "0.00",
        "reductions": "0.00",
        "fbt_type": "Type 1",
        "gross_up_factor": "1.8868",
        "grossed_up_taxable_value": m(grossed_up),
        "fbt_payable": m(fbt_pay),
        "rate_uris_consumed": [],
        "trace": {"applied_rate_table_uris": []},
    }


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# (calc_uri, minimal-valid-standard-body-without-the-field)
_STANDARD_CASES = [
    (
        "urn:sbrm:calculator:fbt:expense-payment",
        {"expenseValue": 2000, "otherwiseDeductiblePercentage": 50,
         "employeeContribution": 200, "fbtType": "Type 1"},
    ),
    (
        "urn:sbrm:calculator:fbt:property",
        {"gstInclusiveValue": 2000, "otherwiseDeductiblePercentage": 0,
         "employeeContribution": 0, "fbtType": "Type 1"},
    ),
    (
        "urn:sbrm:calculator:fbt:residual",
        {"residualValue": 2000, "otherwiseDeductiblePercentage": 0,
         "employeeContribution": 0, "fbtType": "Type 1"},
    ),
]

# (calc_uri, minimal-valid-in-house-body-WITH-the-field)
_INHOUSE_CASES = [
    (
        "urn:sbrm:calculator:fbt:expense-payment-in-house",
        {"expenseValue": 2000, "otherwiseDeductiblePercentage": 50,
         "employeeContribution": 200, "inhouseBenefitClaimed": 1000,
         "fbtType": "Type 1"},
    ),
    (
        "urn:sbrm:calculator:fbt:property-in-house",
        {"gstInclusiveValue": 2000, "otherwiseDeductiblePercentage": 0,
         "employeeContribution": 0, "inhouseBenefitClaimed": 1000,
         "fbtType": "Type 1"},
    ),
    (
        "urn:sbrm:calculator:fbt:residual-in-house",
        {"residualValue": 2000, "otherwiseDeductiblePercentage": 0,
         "employeeContribution": 0, "inhouseBenefitClaimed": 1000,
         "fbtType": "Type 1"},
    ),
]


# --- (a) standard calculators reject the field ------------------------------


@pytest.mark.parametrize("calc_uri,std_body", _STANDARD_CASES,
                         ids=[c[0].rsplit(":", 1)[1] for c in _STANDARD_CASES])
def test_standard_calculator_rejects_inhouse_field_422_extra_forbidden(
    client: TestClient, calc_uri: str, std_body: dict[str, Any]
) -> None:
    """A standard FBT calculator must 422 (extra_forbidden) when the in-house
    field is sent, at loc ["body","inhouseBenefitClaimed"]."""
    body = {**std_body, "inhouseBenefitClaimed": 1000}
    resp = client.post(_url(calc_uri), json=body)
    assert resp.status_code == 422, (
        f"{calc_uri}: expected 422, got {resp.status_code}: {resp.text[:300]}"
    )
    detail = resp.json().get("detail", [])
    assert isinstance(detail, list), detail
    matched = [
        e for e in detail
        if e.get("type") == "extra_forbidden"
        and e.get("loc") == ["body", "inhouseBenefitClaimed"]
    ]
    assert matched, (
        f"{calc_uri}: 422 did not carry extra_forbidden at "
        f'["body","inhouseBenefitClaimed"]: {detail!r}'
    )


# --- (b) in-house calculators still accept + forward the field ---------------


@pytest.mark.parametrize("calc_uri,inhouse_body", _INHOUSE_CASES,
                         ids=[c[0].rsplit(":", 1)[1] for c in _INHOUSE_CASES])
def test_inhouse_calculator_accepts_and_forwards_field(
    client: TestClient, calc_uri: str, inhouse_body: dict[str, Any]
) -> None:
    """An in-house FBT calculator still accepts the field and forwards it to the
    engine as snake_case ``inhouse_benefit_claimed``."""
    with patch(
        "api.routes.calculators.PrologClient.calculate_fbt",
        new=AsyncMock(return_value=_canonical_engine_response()),
    ) as mock_calc:
        resp = client.post(_url(calc_uri), json=inhouse_body)
    assert resp.status_code == 200, (
        f"{calc_uri}: expected 200, got {resp.status_code}: {resp.text[:300]}"
    )
    mock_calc.assert_called_once()
    sent_payload = mock_calc.call_args.args[0]
    assert sent_payload.get("inhouse_benefit_claimed") == 1000, (
        f"{calc_uri}: engine payload missing/!=1000 inhouse_benefit_claimed: "
        f"{sent_payload!r}"
    )


# --- (c) standard expense-payment WITHOUT the field forwards the same body ---


def test_standard_expense_payment_without_field_forwards_same_engine_body(
    client: TestClient,
) -> None:
    """The standard expense-payment request WITHOUT the field forwards an engine
    body that carries NO inhouse_benefit_claimed key (same shape as before)."""
    calc_uri = "urn:sbrm:calculator:fbt:expense-payment"
    body = {
        "expenseValue": 2000,
        "otherwiseDeductiblePercentage": 50,
        "employeeContribution": 200,
        "fbtType": "Type 1",
    }
    with patch(
        "api.routes.calculators.PrologClient.calculate_fbt",
        new=AsyncMock(return_value=_canonical_engine_response()),
    ) as mock_calc:
        resp = client.post(_url(calc_uri), json=body)
    assert resp.status_code == 200, resp.text[:300]
    mock_calc.assert_called_once()
    sent_payload = mock_calc.call_args.args[0]
    assert "inhouse_benefit_claimed" not in sent_payload, (
        "standard expense-payment forwarded inhouse_benefit_claimed to engine: "
        f"{sent_payload!r}"
    )
    # The engine body still carries the standard expense-payment inputs.
    assert sent_payload.get("expense_value") == 2000, sent_payload
    assert sent_payload.get("otherwise_deductible_percentage") == 50, sent_payload
    assert sent_payload.get("employee_contribution") == 200, sent_payload
