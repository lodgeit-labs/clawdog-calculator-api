"""Phase 3 (mut-2026-09-06-mc12) — gateway-side wire assertions for the 6 D19
predicate input schemas per Fable ruling 2026-09-06 02:18 UTC.

The engine-side implementation (LodgeiT_FBT PR #59) makes `fbt_type` required
at the Prolog layer + emits HTTP 400 with a typed refusal envelope carrying
the s.149A message when absent.

Gateway side (this repo): the 6 D19 Pydantic input schemas have `fbt_type` as
a required `Literal["Type 1", "Type 2"]` field. FastAPI/Pydantic rejects
absent → HTTP 422 with `"Field required"` detail. Invalid value ('Type 3',
etc.) → HTTP 422 with literal-error detail.

The 400 vs 422 shape-difference between the two entry points is banked as
a follow-up (a custom `RequestValidationError` handler could map the specific
`fbtType` missing case to 400 with the s.149A message; not in Phase 3 scope
per Fable's "Anything after the flip is a new PR" discipline).

Fable's diagnostic question answered in the PR body:
* `extra="forbid"` was already set on all 6 D19 input models pre-Phase-3.
* Pre-Phase-3 the field was `str | None = Field(None, alias="fbtType")`
  (optional, defaults to None).
* Pre-Phase-3 the gateway was NOT rejecting on absent `fbtType` — wire-
  verified at 2026-09-06 01:47 UTC (housing predicate accepted the omitted
  field + defaulted downstream to Type 2 at the engine).
* Phase 3 change: field re-typed as `Literal["Type 1", "Type 2"]` and marked
  required (`Field(...)` with no default).
"""

from __future__ import annotations

from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.main import app

PERIOD_URI = "urn:sbrm:period:fbt:fy2026"

# 6 D19 predicate URNs (10 gateway routes; some map to same engine predicate)
D19_ROUTES = [
    (
        "urn:sbrm:calculator:fbt:housing",
        {"housingBenefitValue": 6800, "indexationFactor": 1, "recipientRent": 550},
    ),
    (
        "urn:sbrm:calculator:fbt:tebe",
        {"salaryPackagedMealEfle": 0, "recreation": 1000},
    ),
    (
        "urn:sbrm:calculator:fbt:expense-payment",
        {"expenseValue": 2000, "otherwiseDeductiblePercentage": 50, "employeeContribution": 200},
    ),
    (
        "urn:sbrm:calculator:fbt:expense-payment-in-house",
        {"expenseValue": 2000, "otherwiseDeductiblePercentage": 50, "employeeContribution": 200, "inhouseBenefitClaimed": 1000},
    ),
    (
        "urn:sbrm:calculator:fbt:property",
        {"gstInclusiveValue": 1000, "otherwiseDeductiblePercentage": 0, "employeeContribution": 0},
    ),
    (
        "urn:sbrm:calculator:fbt:property-in-house",
        {"gstInclusiveValue": 1000, "otherwiseDeductiblePercentage": 0, "employeeContribution": 0, "inhouseBenefitClaimed": 500},
    ),
    (
        "urn:sbrm:calculator:fbt:residual",
        {"residualValue": 1000, "otherwiseDeductiblePercentage": 0, "employeeContribution": 0},
    ),
    (
        "urn:sbrm:calculator:fbt:residual-in-house",
        {"residualValue": 1000, "otherwiseDeductiblePercentage": 0, "employeeContribution": 0, "inhouseBenefitClaimed": 500},
    ),
    (
        "urn:sbrm:calculator:fbt:meal-entertainment-50-50",
        {"employees": 5000, "employeesAssociates": 3000, "employeesNonassociates": 2000},
    ),
    (
        "urn:sbrm:calculator:fbt:meal-entertainment-register-12wk",
        {"employees": 5000, "employeesAssociates": 3000, "employeesNonassociates": 2000, "registerPercentage": 80},
    ),
]


@pytest.mark.parametrize("calc_uri,valid_body", D19_ROUTES)
def test_absent_fbtType_rejected_at_gateway_pydantic_layer(
    calc_uri: str, valid_body: dict[str, object]
) -> None:
    """Absent `fbtType` → HTTP 422 at gateway (Pydantic `Field(...)` required)."""
    with TestClient(app) as client:
        url = f"/v1/calculators/{quote(calc_uri, safe='')}/{quote(PERIOD_URI, safe='')}"
        resp = client.post(url, json=valid_body)  # no fbtType

    assert resp.status_code == 422, (
        f"{calc_uri} accepted absent fbtType: got {resp.status_code}. "
        f"Expected 422 (Pydantic Field required)."
    )
    body = resp.json()
    detail = body.get("detail", [])
    # Detail is a list of validation errors; find one for fbtType
    assert any(
        (err.get("loc") == ["body", "fbtType"] or "fbtType" in err.get("loc", []))
        and err.get("type") == "missing"
        for err in detail
    ), f"{calc_uri} 422 did not name fbtType as missing: {detail!r}"


@pytest.mark.parametrize("calc_uri,valid_body", D19_ROUTES)
def test_invalid_fbtType_rejected_at_gateway_pydantic_layer(
    calc_uri: str, valid_body: dict[str, object]
) -> None:
    """Invalid `fbtType` value ('Type 3', etc.) → HTTP 422 (Literal enum error)."""
    with TestClient(app) as client:
        url = f"/v1/calculators/{quote(calc_uri, safe='')}/{quote(PERIOD_URI, safe='')}"
        resp = client.post(url, json={**valid_body, "fbtType": "Type 3"})

    assert resp.status_code == 422, (
        f"{calc_uri} accepted invalid fbtType='Type 3': got {resp.status_code}. "
        f"Expected 422 (Pydantic Literal error)."
    )
    body = resp.json()
    detail = body.get("detail", [])
    assert any(
        (err.get("loc") == ["body", "fbtType"] or "fbtType" in err.get("loc", []))
        and err.get("type") == "literal_error"
        for err in detail
    ), f"{calc_uri} 422 did not name fbtType as literal_error: {detail!r}"
