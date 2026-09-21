"""HP anchor fixture v1.1 specification tests.

Tests the hire purchase amortisation semantics defined in
tests/fixtures/hp/anchors_v1_1.json against pure Decimal schedule generation.

This module must not import anything from api/; it is the spec, not the
implementation. The fixtures are wire-truth anchors from LodgeiT reports
(hp/176, hp/252, hp/227) and the NAB Scania contract.

Semantics enforced:
- Nominal annual rate / 12 per monthly period
- Unrounded internal balances; display rounded ROUND_HALF_UP to cents
- In-arrears: row interest = opening balance × r, payment after
- In-advance: row 1 interest 0.00; payment first
- Balloon replaces the regular instalment on its row
- Identity: current_net + non_current_net = principal_balance − final_balance (≤ 0.01)

Negative result enforced:
- Per-row interest rounding must NOT reproduce Scania/Wacker totals
"""
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "hp" / "anchors_v1_2.json"

def _add_months(date, months: int):
    """Add months to a date, clamping day to valid range."""
    import calendar
    from datetime import datetime

    target_month = date.month + months
    target_year = date.year + (target_month - 1) // 12
    target_month = ((target_month - 1) % 12) + 1

    # Clamp day to last day of target month
    max_day = calendar.monthrange(target_year, target_month)[1]
    target_day = min(date.day, max_day)

    return datetime(target_year, target_month, target_day)



def _load_fixtures():
    """Load and parse the anchor fixtures."""
    with FIXTURES_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _round_display(value: Decimal) -> Decimal:
    """Round to cents using ROUND_HALF_UP for display."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _generate_schedule(
    principal: Decimal,
    rate_annual_pct: Decimal,
    term: int,
    instalment: Decimal,
    timing: str,
    balloon: dict | None,
) -> list[dict]:
    """Generate amortisation schedule with unrounded internal balances.

    Args:
        principal: Loan amount
        rate_annual_pct: Annual rate as percentage (e.g. 9.153)
        term: Number of regular instalments (excludes balloon row)
        instalment: Regular payment amount
        timing: "in_arrears" or "in_advance"
        balloon: {"amount": Decimal, "row": int} or None

    Returns:
        List of dicts: {"row", "interest", "principal_portion", "payment", "balance"}
    """
    rate_periodic = rate_annual_pct / Decimal("100") / Decimal("12")
    balance = principal
    schedule = []

    total_rows = term if not balloon else max(term, balloon["row"])

    for row in range(1, total_rows + 1):
        # Determine if this row has a balloon payment
        balloon_amt = Decimal("0")
        if balloon and row == balloon["row"]:
            balloon_amt = balloon["amount"]

        # Determine regular payment (0 if this is a balloon-only row beyond term)
        regular_payment = instalment if row <= term else Decimal("0")
        total_payment = regular_payment + balloon_amt

        # Calculate interest
        if timing == "in_advance" and row == 1:
            interest = Decimal("0")
        else:
            interest = balance * rate_periodic

        # Principal portion
        principal_portion = total_payment - interest

        # New balance (unrounded internally)
        balance = balance - principal_portion

        schedule.append({
            "row": row,
            "interest": interest,
            "principal_portion": principal_portion,
            "payment": total_payment,
            "balance": balance,
        })

    return schedule


def _sum_fy_interest(schedule: list[dict], begin_date: str, fy_year: int) -> Decimal:
    """Sum interest for a financial year (Jul 1 - Jun 30).

    Args:
        schedule: Schedule rows with "row" and "interest"
        begin_date: Contract start date (YYYY-MM-DD)
        fy_year: FY year (e.g. 2017 for FY2016-17 = Jul 2016 - Jun 2017)

    Returns:
        Sum of interest for rows falling in that FY
    """
    from datetime import datetime



    begin = datetime.fromisoformat(begin_date)
    fy_start = datetime(fy_year - 1, 7, 1)
    fy_end = datetime(fy_year, 6, 30)

    total = Decimal("0")
    for row_data in schedule:
        row_num = row_data["row"]
        row_date = _add_months(begin, row_num - 1)

        if fy_start <= row_date <= fy_end:
            total += row_data["interest"]

    return total


def _calculate_split(
    schedule: list[dict],
    balance_date: str,
    begin_date: str,
    principal_balance: Decimal,
) -> dict:
    """Calculate liability split at a balance date.

    Args:
        schedule: Full schedule
        balance_date: Balance sheet date (YYYY-MM-DD)
        begin_date: Contract start date
        principal_balance: Principal outstanding at balance_date

    Returns:
        Dict with current_gross, current_unexpired, non_current_gross,
        non_current_unexpired, current_net, non_current_net
    """
    from datetime import datetime



    balance_dt = datetime.fromisoformat(balance_date)
    begin = datetime.fromisoformat(begin_date)

    # Find rows after balance date
    current_rows = []  # next 12 months
    non_current_rows = []  # beyond 12 months

    for row_data in schedule:
        row_num = row_data["row"]
        row_date = _add_months(begin, row_num - 1)

        if row_date > balance_dt:
            months_out = (row_date.year - balance_dt.year) * 12 + (row_date.month - balance_dt.month)
            if months_out <= 12:
                current_rows.append(row_data)
            else:
                non_current_rows.append(row_data)

    current_gross = sum(r["payment"] for r in current_rows)
    current_unexpired = sum(r["interest"] for r in current_rows)
    non_current_gross = sum(r["payment"] for r in non_current_rows)
    non_current_unexpired = sum(r["interest"] for r in non_current_rows)

    current_net = current_gross - current_unexpired
    non_current_net = non_current_gross - non_current_unexpired

    return {
        "current_gross": current_gross,
        "current_unexpired": current_unexpired,
        "non_current_gross": non_current_gross,
        "non_current_unexpired": non_current_unexpired,
        "current_net": current_net,
        "non_current_net": non_current_net,
    }


@pytest.fixture(scope="module")
def fixtures():
    """Load fixtures once per module."""
    return _load_fixtures()


@pytest.mark.parametrize("contract_idx", [0, 1, 2])
def test_hp_anchor_values(fixtures, contract_idx):
    """Test each contract's anchor values against pure Decimal schedule.

    Anchors use the stated rate (from LodgeiT reports), not the solved rate.
    """
    contract = fixtures["contracts"][contract_idx]

    principal = Decimal(contract["amount"])
    rate_pct = Decimal(contract["rate_pct_stated"])  # Use stated rate for anchors
    term = contract["term"]
    instalment = Decimal(contract["instalment"])
    timing = contract["timing"]

    balloon = None
    if contract["balloon"]:
        balloon = {
            "amount": Decimal(contract["balloon"]["amount"]),
            "row": contract["balloon"]["row"],
        }

    schedule = _generate_schedule(principal, rate_pct, term, instalment, timing, balloon)

    # Assert anchor values
    anchors = contract["anchors"]

    first_interest_display = _round_display(schedule[0]["interest"])
    assert str(first_interest_display) == anchors["first_interest"], (
        f"{contract['name']}: first_interest mismatch"
    )

    if "row2_interest" in anchors:
        row2_interest_display = _round_display(schedule[1]["interest"])
        assert str(row2_interest_display) == anchors["row2_interest"], (
            f"{contract['name']}: row2_interest mismatch"
        )

    total_interest = sum(r["interest"] for r in schedule)
    total_interest_display = _round_display(total_interest)
    assert str(total_interest_display) == anchors["total_interest"], (
        f"{contract['name']}: total_interest mismatch"
    )

    total_payments = sum(r["payment"] for r in schedule)
    total_payments_display = _round_display(total_payments)
    assert str(total_payments_display) == anchors["total_payments"], (
        f"{contract['name']}: total_payments mismatch"
    )

    final_balance_display = _round_display(schedule[-1]["balance"])
    assert str(final_balance_display) == anchors["final_balance"], (
        f"{contract['name']}: final_balance mismatch"
    )


@pytest.mark.parametrize("contract_idx", [0, 1, 2])
def test_hp_fy_interest(fixtures, contract_idx):
    """Test FY interest sums for each contract.

    Uses stated rate to match LodgeiT report figures.
    """
    contract = fixtures["contracts"][contract_idx]

    principal = Decimal(contract["amount"])
    rate_pct = Decimal(contract["rate_pct_stated"])  # Use stated rate
    term = contract["term"]
    instalment = Decimal(contract["instalment"])
    timing = contract["timing"]
    begin_date = contract["begin"]

    balloon = None
    if contract["balloon"]:
        balloon = {
            "amount": Decimal(contract["balloon"]["amount"]),
            "row": contract["balloon"]["row"],
        }

    schedule = _generate_schedule(principal, rate_pct, term, instalment, timing, balloon)

    fy_interest = contract["anchors"]["fy_interest"]

    for fy_year_str, expected_str in fy_interest.items():
        fy_year = int(fy_year_str)
        computed = _sum_fy_interest(schedule, begin_date, fy_year)
        computed_display = _round_display(computed)
        assert str(computed_display) == expected_str, (
            f"{contract['name']}: FY{fy_year} interest mismatch"
        )


@pytest.mark.parametrize("contract_idx", [0, 2])  # Toyota and Wacker have splits
def test_hp_liability_split(fixtures, contract_idx):
    """Test liability split calculations.

    Uses stated rate to match LodgeiT report figures.
    """
    contract = fixtures["contracts"][contract_idx]

    # Find the split key (e.g., "split_2016-06-30")
    split_key = None
    for key in contract.keys():
        if key.startswith("split_"):
            split_key = key
            break

    if not split_key:
        pytest.skip(f"{contract['name']}: no split data")

    balance_date = split_key.replace("split_", "")
    split_expected = contract[split_key]

    principal = Decimal(contract["amount"])
    rate_pct = Decimal(contract["rate_pct_stated"])  # Use stated rate
    term = contract["term"]
    instalment = Decimal(contract["instalment"])
    timing = contract["timing"]
    begin_date = contract["begin"]

    balloon = None
    if contract["balloon"]:
        balloon = {
            "amount": Decimal(contract["balloon"]["amount"]),
            "row": contract["balloon"]["row"],
        }

    schedule = _generate_schedule(principal, rate_pct, term, instalment, timing, balloon)

    # Compute principal balance at balance_date from the schedule
    from datetime import datetime



    balance_dt = datetime.fromisoformat(balance_date)
    begin = datetime.fromisoformat(begin_date)

    # Find the last row on or before balance_date
    principal_balance = principal
    for row_data in schedule:
        row_num = row_data["row"]
        row_date = _add_months(begin, row_num - 1)
        if row_date <= balance_dt:
            principal_balance = row_data["balance"]
        else:
            break

    split = _calculate_split(schedule, balance_date, begin_date, principal_balance)

    # Assert each split value
    for key in ["current_gross", "current_unexpired", "non_current_gross", "non_current_unexpired"]:
        computed_display = _round_display(split[key])
        assert str(computed_display) == split_expected[key], (
            f"{contract['name']}: {key} mismatch at {balance_date}"
        )

    # Assert identity: current_net + non_current_net == principal_balance - final_balance
    final_balance = _round_display(schedule[-1]["balance"])
    identity_lhs = split["current_net"] + split["non_current_net"]
    identity_rhs = principal_balance - final_balance
    identity_lhs_display = _round_display(identity_lhs)
    identity_rhs_display = _round_display(identity_rhs)

    delta = abs(identity_lhs_display - identity_rhs_display)
    print(f"IDENTITY DELTA {contract['name']} @ {balance_date}: {delta}")
    assert delta <= Decimal("0.01"), (
        f"{contract['name']}: identity failed at {balance_date}: "
        f"{identity_lhs_display} != {identity_rhs_display} (delta {delta})"
    )


def test_hp_scania_split_with_balloon(fixtures):
    """Test Scania split separately since it has a balloon.

    Uses stated rate to match LodgeiT report figures.
    """
    contract = fixtures["contracts"][1]  # Scania
    assert contract["name"] == "Scania White Prime Mover"

    split_key = "split_2025-06-30"
    balance_date = "2025-06-30"
    split_expected = contract[split_key]

    principal = Decimal(contract["amount"])
    rate_pct = Decimal(contract["rate_pct_stated"])  # Use stated rate
    term = contract["term"]
    instalment = Decimal(contract["instalment"])
    timing = contract["timing"]
    begin_date = contract["begin"]

    balloon = {
        "amount": Decimal(contract["balloon"]["amount"]),
        "row": contract["balloon"]["row"],
    }

    schedule = _generate_schedule(principal, rate_pct, term, instalment, timing, balloon)

    # Compute principal balance at balance_date from the schedule
    from datetime import datetime



    balance_dt = datetime.fromisoformat(balance_date)
    begin = datetime.fromisoformat(begin_date)

    # Find the last row on or before balance_date
    principal_balance = principal
    for row_data in schedule:
        row_num = row_data["row"]
        row_date = _add_months(begin, row_num - 1)
        if row_date <= balance_dt:
            principal_balance = row_data["balance"]
        else:
            break

    split = _calculate_split(schedule, balance_date, begin_date, principal_balance)

    # Assert each split value
    for key in ["current_gross", "current_unexpired", "non_current_gross", "non_current_unexpired"]:
        computed_display = _round_display(split[key])
        assert str(computed_display) == split_expected[key], (
            f"Scania: {key} mismatch at {balance_date}"
        )

    # Assert identity: current_net + non_current_net == principal_balance - final_balance
    final_balance = _round_display(schedule[-1]["balance"])
    identity_lhs = split["current_net"] + split["non_current_net"]
    identity_rhs = principal_balance - final_balance
    identity_lhs_display = _round_display(identity_lhs)
    identity_rhs_display = _round_display(identity_rhs)

    delta = abs(identity_lhs_display - identity_rhs_display)
    print(f"IDENTITY DELTA Scania @ {balance_date}: {delta}")
    assert delta <= Decimal("0.01"), (
        f"Scania: identity failed at {balance_date}: "
        f"{identity_lhs_display} != {identity_rhs_display} (delta {delta})"
    )


@pytest.mark.parametrize("contract_name,contract_idx", [("Scania", 1), ("Wacker", 2)])
def test_hp_negative_per_row_rounding(fixtures, contract_name, contract_idx):
    """Test that per-row interest rounding does NOT reproduce totals.

    The negative result from the fixture: per-row interest rounding produces
    different totals and final balances for Scania and Wacker when using the
    stated rate (the test uses stated rate to match the anchor generation).
    """
    contract = fixtures["contracts"][contract_idx]

    principal = Decimal(contract["amount"])
    rate_pct = Decimal(contract["rate_pct_stated"])  # Use stated rate
    term = contract["term"]
    instalment = Decimal(contract["instalment"])
    timing = contract["timing"]

    balloon = None
    if contract["balloon"]:
        balloon = {
            "amount": Decimal(contract["balloon"]["amount"]),
            "row": contract["balloon"]["row"],
        }

    # Generate schedule with PER-ROW interest rounding
    rate_periodic = rate_pct / Decimal("100") / Decimal("12")
    balance = principal
    schedule_rounded = []

    total_rows = term if not balloon else max(term, balloon["row"])

    for row in range(1, total_rows + 1):
        balloon_amt = Decimal("0")
        if balloon and row == balloon["row"]:
            balloon_amt = balloon["amount"]

        regular_payment = instalment if row <= term else Decimal("0")
        total_payment = regular_payment + balloon_amt

        if timing == "in_advance" and row == 1:
            interest_raw = Decimal("0")
        else:
            interest_raw = balance * rate_periodic

        # Round interest per row
        interest = _round_display(interest_raw)
        principal_portion = total_payment - interest
        balance = balance - principal_portion

        schedule_rounded.append({
            "row": row,
            "interest": interest,
            "balance": balance,
        })

    total_interest_rounded = sum(r["interest"] for r in schedule_rounded)
    final_balance_rounded = _round_display(schedule_rounded[-1]["balance"])

    # Expected (unrounded internal) values
    anchors = contract["anchors"]
    expected_total = Decimal(anchors["total_interest"])
    expected_final = Decimal(anchors["final_balance"])

    # Assert they do NOT match
    assert total_interest_rounded != expected_total, (
        f"{contract_name}: per-row rounding unexpectedly matched total_interest"
    )
    assert final_balance_rounded != expected_final, (
        f"{contract_name}: per-row rounding unexpectedly matched final_balance"
    )
