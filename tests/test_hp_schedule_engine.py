"""Engine tests for the hire purchase schedule calculator (module hp).

Unlike tests/test_hp_anchors.py (which is the pure-spec test that imports no
api/ code), this module imports the engine api.engines.hp.schedule and asserts
that the engine reproduces the same anchors, FY interest, splits and identity
as the spec, plus engine-specific behaviour: balloon mode add, the
balloon-mode-required refusal, and the unsupported-frequency refusal.

Identity: current_net + non_current_net == principal_balance - final_balance,
to within 0.01 (one cent of summation rounding). No wider tolerance.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from api.engines.hp.schedule import HpEngineError, compute_schedule

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "hp" / "anchors_v1_2.json"
_TOL = Decimal("0.01")


def _load_fixtures() -> dict:
    with FIXTURES_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _run(contract: dict) -> dict:
    """Run the engine for a fixture contract at its stated rate, replace mode."""
    balloon = None
    if contract["balloon"]:
        balloon = {
            "amount": contract["balloon"]["amount"],
            "instalment_number": contract["balloon"]["row"],
            "mode": "replace",
        }
    return compute_schedule(
        amount_financed=contract["amount"],
        annual_rate_pct=contract["rate_pct_stated"],
        term_regular_instalments=contract["term"],
        instalment=contract["instalment"],
        timing=contract["timing"],
        frequency="monthly",
        begin_date=contract["begin"],
        contract_form="hire_purchase",
        balloon=balloon,
        fy_end_month=6,
    )


@pytest.fixture(scope="module")
def fixtures() -> dict:
    return _load_fixtures()


@pytest.mark.parametrize("contract_idx", [0, 1, 2])
def test_engine_anchor_values(fixtures, contract_idx):
    """Engine reproduces first_interest, total_interest, final_balance."""
    contract = fixtures["contracts"][contract_idx]
    result = _run(contract)
    anchors = contract["anchors"]

    assert result["rows"][0]["interest"] == anchors["first_interest"], (
        f"{contract['name']}: first_interest"
    )
    if "row2_interest" in anchors:
        assert result["rows"][1]["interest"] == anchors["row2_interest"], (
            f"{contract['name']}: row2_interest"
        )
    assert result["totals"]["interest"] == anchors["total_interest"], (
        f"{contract['name']}: total_interest"
    )
    assert result["totals"]["payments"] == anchors["total_payments"], (
        f"{contract['name']}: total_payments"
    )
    assert result["final_balance"] == anchors["final_balance"], (
        f"{contract['name']}: final_balance"
    )
    # Residual is the final balance, reported, never forced to zero.
    assert result["rate_precision_residual"] == anchors["final_balance"], (
        f"{contract['name']}: rate_precision_residual"
    )


@pytest.mark.parametrize("contract_idx", [0, 1, 2])
def test_engine_fy_interest(fixtures, contract_idx):
    """Engine reproduces the FY interest allocation (Jul-Jun)."""
    contract = fixtures["contracts"][contract_idx]
    result = _run(contract)
    for fy_year, expected in contract["anchors"]["fy_interest"].items():
        assert result["fy_interest"].get(fy_year) == expected, (
            f"{contract['name']}: FY{fy_year} interest "
            f"{result['fy_interest'].get(fy_year)} != {expected}"
        )


@pytest.mark.parametrize("contract_idx", [0, 1, 2])
def test_engine_splits_and_identity(fixtures, contract_idx):
    """Engine reproduces the liability split and the identity at each split date.

    Identity: current_net + non_current_net == principal_balance - final_balance,
    to within 0.01.
    """
    contract = fixtures["contracts"][contract_idx]
    result = _run(contract)
    final_balance = Decimal(result["final_balance"])

    split_keys = [k for k in contract if k.startswith("split_")]
    assert split_keys, f"{contract['name']}: fixture has no split data"

    for split_key in split_keys:
        balance_date = split_key.replace("split_", "")
        expected = contract[split_key]
        position = result["fy_position"].get(balance_date)
        assert position is not None, (
            f"{contract['name']}: engine produced no fy_position for {balance_date}"
        )

        for field in (
            "principal",
            "current_gross",
            "current_unexpired",
            "non_current_gross",
            "non_current_unexpired",
        ):
            assert position[field] == expected[field], (
                f"{contract['name']}: {field} at {balance_date} "
                f"{position[field]} != {expected[field]}"
            )

        current_net = Decimal(position["current_net"])
        non_current_net = Decimal(position["non_current_net"])
        principal_balance = Decimal(position["principal"])

        identity_lhs = current_net + non_current_net
        identity_rhs = principal_balance - final_balance
        delta = abs(identity_lhs - identity_rhs)
        assert delta <= _TOL, (
            f"{contract['name']}: identity failed at {balance_date}: "
            f"{identity_lhs} != {identity_rhs} (delta {delta})"
        )


def test_engine_balloon_mode_add_scania():
    """Scania with balloon mode 'add' makes row 60 the instalment plus the balloon.

    Row 60 payment = 4180.02 + 59180.02 = 63360.04, and the final balance moves
    accordingly (the extra regular instalment overpays the residual).
    """
    result = compute_schedule(
        amount_financed="273269.35",
        annual_rate_pct="3.84",
        term_regular_instalments=59,
        instalment="4180.02",
        timing="in_arrears",
        frequency="monthly",
        begin_date="2021-08-30",
        contract_form="chattel_mortgage",
        balloon={"amount": "59180.02", "instalment_number": 60, "mode": "add"},
        fy_end_month=6,
    )
    assert result["rows"][59]["payment"] == "63360.04", (
        f"row 60 payment {result['rows'][59]['payment']} != 63360.04"
    )
    # The extra instalment overpays: final balance is -4179.91.
    assert result["final_balance"] == "-4179.91", (
        f"final_balance {result['final_balance']} != -4179.91"
    )
    assert result["rate_precision_residual"] == "-4179.91"


def test_engine_balloon_missing_mode_refuses():
    """A balloon without a mode is refused (422) naming the field."""
    with pytest.raises(HpEngineError) as exc_info:
        compute_schedule(
            amount_financed="273269.35",
            annual_rate_pct="3.84",
            term_regular_instalments=59,
            instalment="4180.02",
            timing="in_arrears",
            frequency="monthly",
            begin_date="2021-08-30",
            contract_form="chattel_mortgage",
            balloon={"amount": "59180.02", "instalment_number": 60},
            fy_end_month=6,
        )
    err = exc_info.value
    assert err.status_code == 422
    assert err.refusal_class == "balloon_mode_required"
    assert err.field == "balloon.mode"


def test_engine_unsupported_frequency_refuses():
    """A non-monthly frequency is refused (400) with refusal_class."""
    with pytest.raises(HpEngineError) as exc_info:
        compute_schedule(
            amount_financed="31000",
            annual_rate_pct="9.153",
            term_regular_instalments=60,
            instalment="645.82",
            timing="in_arrears",
            frequency="quarterly",
            begin_date="2016-05-27",
            contract_form="hire_purchase",
            balloon=None,
            fy_end_month=6,
        )
    err = exc_info.value
    assert err.status_code == 400
    assert err.refusal_class == "unsupported_frequency"
    assert err.field == "frequency"


def test_engine_manifest_and_advisory():
    """Manifest and advisory carry the required identity + narrative fields."""
    result = compute_schedule(
        amount_financed="31000",
        annual_rate_pct="9.153",
        term_regular_instalments=60,
        instalment="645.82",
        timing="in_arrears",
        frequency="monthly",
        begin_date="2016-05-27",
        contract_form="hire_purchase",
        balloon=None,
        fy_end_month=6,
    )
    manifest = result["manifest"]
    assert manifest["calculator"] == "urn:sbrm:calculator:hp:schedule"
    assert manifest["accrual_basis"] == "nominal_monthly_period"
    assert manifest["engine_version"]

    advisory = result["advisory"]
    assert advisory["figure_type"] == "amortisation_schedule"
    assert any("residual" in note for note in advisory["notes"])
    assert any("payment_date" in note for note in advisory["notes"])
