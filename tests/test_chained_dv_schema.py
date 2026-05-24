"""Schema-level test for OT #81 chained-DV input fields.

Verifies the Pydantic ``FBTCarOperatingCostInput`` schema accepts the
``acquisition_cost`` field (added in ``mut-2026-05-24-mc09`` per Brain
PR #259 incident closure + Finding #2 follow-up). The corresponding engine
predicate (``fbt_car_oc_deemed_amounts_chained/9``) shipped in
``lodgeit-labs/LodgeiT_FBT`` PR #26 (OT #81 Rung 3 mc08-2026-05-22) and is
live in production at
``https://fbt-engine-8340695160.australia-southeast1.run.app/calculate_fbt``
(verified 2026-05-24 10:42 UTC: all 3 NTAA reference rows byte-exact).

Before this PR, the API's Pydantic schema declared ``extra="forbid"`` and
rejected ``acquisition_cost`` with HTTP 422 ``extra_forbidden`` (Finding #2
surfaced 2026-05-24 10:42 UTC via live API probe). The bridge could not
forward chained-DV requests to the engine even though the engine path is
live and byte-exact against NTAA.

This test is the schema-level binary-failure gate that the field is in the
contract. The full end-to-end test against a mocked chained-DV engine
response is deliberately deferred until a recorded engine fixture is
available (Lesson #31 — keep this PR scoped to the schema change).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.schemas.invocation import FBTCarOperatingCostInput

_BASE_INPUT = {
    "business_use_percentage": 75,
    "form_of_finance": "owned",
    "fuel_repairs_servicing": 3000,
    "registration_insurance": 1500,
    "employee_contribution": 200,
    "no_private_use_reduction": 0,
    "acquisition_date": "2024-01-01",
}


def test_acquisition_cost_accepted_snake_case() -> None:
    """`acquisition_cost` is accepted in snake_case (engine-canonical shape)."""
    payload = {**_BASE_INPUT, "acquisition_cost": 50000}
    m = FBTCarOperatingCostInput(**payload)
    assert m.acquisition_cost == 50000.0
    # Round-trip via model_dump(by_alias=False) — this is what
    # api/routes/calculators.py uses when forwarding to the Prolog engine.
    dumped = m.model_dump(by_alias=False, exclude_none=True)
    assert dumped["acquisition_cost"] == 50000.0
    assert dumped["acquisition_date"] == "2024-01-01"


def test_acquisition_cost_accepted_camel_case_alias() -> None:
    """`acquisitionCost` (camelCase alias) is accepted for fbt_tester.py parity."""
    payload = {
        "businessUsePercentage": 75,
        "formOfFinance": "owned",
        "fuelRepairsServicing": 3000,
        "registrationInsurance": 1500,
        "employeeContribution": 200,
        "noPrivateUseReduction": 0,
        "acquisitionDate": "2024-01-01",
        "acquisitionCost": 50000,
    }
    m = FBTCarOperatingCostInput(**payload)
    assert m.acquisition_cost == 50000.0


def test_acquisition_cost_negative_rejected() -> None:
    """Negative `acquisition_cost` is rejected by `ge=0` constraint."""
    payload = {**_BASE_INPUT, "acquisition_cost": -1}
    with pytest.raises(ValidationError):
        FBTCarOperatingCostInput(**payload)


def test_chained_dv_input_round_trip_to_engine_shape() -> None:
    """The full chained-DV input set round-trips to the engine payload shape.

    Mirrors the verifier's `build_car_oc_payload` for `s11_chained_row5` —
    the NTAA Row 5 in-FY-acquisition case — and confirms every field the
    engine consumes is present after `model_dump(by_alias=False, exclude_none=True)`.
    """
    payload = {
        "businessUsePercentage": 75,
        "formOfFinance": "owned",
        "fuelRepairsServicing": 0,
        "registrationInsurance": 0,
        "employeeContribution": 0,
        "noPrivateUseReduction": 0,
        "acquisitionCost": 45000,
        "acquisitionDate": "2025-10-01",
        "daysHeldInFBTYear": 182,
    }
    m = FBTCarOperatingCostInput(**payload)
    dumped = m.model_dump(by_alias=False, exclude_none=True)

    # Every engine-consumed field present at the payload root.
    expected_keys = {
        "business_use_percentage",
        "form_of_finance",
        "fuel_repairs_servicing",
        "registration_insurance",
        "employee_contribution",
        "no_private_use_reduction",
        "acquisition_cost",
        "acquisition_date",
        "days_held_in_fbt_year",
    }
    assert expected_keys.issubset(dumped.keys())
    assert dumped["acquisition_cost"] == 45000.0
    assert dumped["days_held_in_fbt_year"] == 182
