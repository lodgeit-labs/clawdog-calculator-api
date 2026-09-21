"""Hire purchase amortisation schedule engine (module hp).

Pure ``decimal.Decimal`` throughout: no floats anywhere. Semantics are the
executable specification in ``tests/test_hp_anchors.py`` (calc URN
``urn:sbrm:calculator:hp:schedule``):

- nominal annual rate / 12 per monthly period;
- internal balances carried unrounded; ROUND_HALF_UP to cents only at output;
- in-advance row 1 interest is 0.00;
- balloon lands on its instalment row per its mode (replace | add);
- rate_precision_residual is the final balance and is never forced to zero.

The engine emits refusals as ``HpEngineError`` carrying an HTTP status and a
``refusal_class``; the route handler maps these to HTTP responses.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

ENGINE_VERSION = "hp-schedule-1.0.0"
CALCULATOR_URN = "urn:sbrm:calculator:hp:schedule"
ACCRUAL_BASIS = "nominal_monthly_period"

_CENTS = Decimal("0.01")
_TWELVE = Decimal("12")
_HUNDRED = Decimal("100")

_VALID_TIMING = ("in_arrears", "in_advance")
_VALID_BALLOON_MODES = ("replace", "add")
_VALID_CONTRACT_FORMS = ("hire_purchase", "chattel_mortgage", "equipment_loan")


class HpEngineError(Exception):
    """Structured refusal from the HP engine.

    Attributes:
        status_code: HTTP status the route handler should return.
        refusal_class: machine-readable refusal identifier.
        field: the offending field name, when applicable.
    """

    def __init__(
        self,
        message: str,
        status_code: int,
        refusal_class: str,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.refusal_class = refusal_class
        self.field = field


@dataclass(frozen=True)
class Balloon:
    """A balloon payment on a specific instalment row."""

    amount: Decimal
    instalment_number: int
    mode: str  # replace | add


def _q(value: Decimal) -> str:
    """Round to cents (ROUND_HALF_UP) and render as a decimal string."""
    return str(value.quantize(_CENTS, rounding=ROUND_HALF_UP))


def _round_cents(value: Decimal) -> Decimal:
    """Round to cents (ROUND_HALF_UP)."""
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _add_months(base: date, months: int) -> date:
    """Add whole months to a date, clamping the day to the target month's last."""
    target_month = base.month + months
    target_year = base.year + (target_month - 1) // 12
    target_month = ((target_month - 1) % 12) + 1
    max_day = calendar.monthrange(target_year, target_month)[1]
    target_day = min(base.day, max_day)
    return date(target_year, target_month, target_day)


def _to_decimal(value: str, field: str) -> Decimal:
    """Parse a decimal string, refusing anything Decimal cannot accept."""
    try:
        return Decimal(value)
    except Exception as exc:  # noqa: BLE001 — surfaced as a structured refusal
        raise HpEngineError(
            f"{field}={value!r} is not a valid decimal string.",
            status_code=422,
            refusal_class="invalid_decimal",
            field=field,
        ) from exc


def compute_schedule(
    *,
    amount_financed: str,
    annual_rate_pct: str,
    term_regular_instalments: int,
    instalment: str,
    timing: str,
    frequency: str,
    begin_date: str,
    contract_form: str,
    balloon: dict | None = None,
    fy_end_month: int = 6,
) -> dict:
    """Compute a hire purchase amortisation schedule.

    All money inputs are decimal strings; all money outputs are decimal
    strings rounded to cents at output only. Raises :class:`HpEngineError`
    for refusals.
    """
    # --- frequency: monthly only in v1 -----------------------------------
    if frequency != "monthly":
        raise HpEngineError(
            f"frequency={frequency!r} is not supported in v1 (monthly only).",
            status_code=400,
            refusal_class="unsupported_frequency",
            field="frequency",
        )

    # --- timing ----------------------------------------------------------
    if timing not in _VALID_TIMING:
        raise HpEngineError(
            f"timing={timing!r} must be one of {list(_VALID_TIMING)}.",
            status_code=422,
            refusal_class="invalid_timing",
            field="timing",
        )

    # --- contract_form (required) ----------------------------------------
    if contract_form not in _VALID_CONTRACT_FORMS:
        raise HpEngineError(
            f"contract_form={contract_form!r} must be one of "
            f"{list(_VALID_CONTRACT_FORMS)}.",
            status_code=422,
            refusal_class="invalid_contract_form",
            field="contract_form",
        )

    # --- term ------------------------------------------------------------
    if term_regular_instalments < 1:
        raise HpEngineError(
            "term_regular_instalments must be a positive integer.",
            status_code=422,
            refusal_class="invalid_term",
            field="term_regular_instalments",
        )

    # --- begin_date ------------------------------------------------------
    try:
        begin = date.fromisoformat(begin_date)
    except ValueError as exc:
        raise HpEngineError(
            f"begin_date={begin_date!r} is not an ISO date (YYYY-MM-DD).",
            status_code=422,
            refusal_class="invalid_date",
            field="begin_date",
        ) from exc

    # --- fy_end_month ----------------------------------------------------
    if not (1 <= fy_end_month <= 12):
        raise HpEngineError(
            "fy_end_month must be between 1 and 12.",
            status_code=422,
            refusal_class="invalid_fy_end_month",
            field="fy_end_month",
        )

    # --- balloon (mode required when balloon present, no default) --------
    parsed_balloon: Balloon | None = None
    if balloon is not None:
        if "mode" not in balloon or balloon.get("mode") is None:
            raise HpEngineError(
                "balloon.mode is required when balloon is present "
                "(one of 'replace' | 'add'); there is no default.",
                status_code=422,
                refusal_class="balloon_mode_required",
                field="balloon.mode",
            )
        mode = balloon["mode"]
        if mode not in _VALID_BALLOON_MODES:
            raise HpEngineError(
                f"balloon.mode={mode!r} must be one of {list(_VALID_BALLOON_MODES)}.",
                status_code=422,
                refusal_class="invalid_balloon_mode",
                field="balloon.mode",
            )
        if "amount" not in balloon or "instalment_number" not in balloon:
            raise HpEngineError(
                "balloon requires 'amount' and 'instalment_number'.",
                status_code=422,
                refusal_class="balloon_incomplete",
                field="balloon",
            )
        parsed_balloon = Balloon(
            amount=_to_decimal(str(balloon["amount"]), "balloon.amount"),
            instalment_number=int(balloon["instalment_number"]),
            mode=mode,
        )

    principal = _to_decimal(amount_financed, "amount_financed")
    rate_annual_pct = _to_decimal(annual_rate_pct, "annual_rate_pct")
    instalment_dec = _to_decimal(instalment, "instalment")

    rate_periodic = rate_annual_pct / _HUNDRED / _TWELVE

    term = term_regular_instalments
    balloon_row = parsed_balloon.instalment_number if parsed_balloon else 0
    total_rows = max(term, balloon_row) if parsed_balloon else term

    balance = principal
    rows: list[dict] = []

    for row_num in range(1, total_rows + 1):
        opening = balance

        # Balloon contribution on its row, by mode.
        balloon_amt = Decimal("0")
        if parsed_balloon and row_num == parsed_balloon.instalment_number:
            balloon_amt = parsed_balloon.amount

        regular_payment = instalment_dec if row_num <= term else Decimal("0")

        if parsed_balloon and row_num == parsed_balloon.instalment_number:
            if parsed_balloon.mode == "replace":
                # The balloon replaces the instalment on its row.
                total_payment = balloon_amt
            else:  # add
                # The balloon is paid in addition to the regular instalment on
                # its row, even when that row sits beyond the regular term.
                total_payment = instalment_dec + balloon_amt
        else:
            total_payment = regular_payment

        # Interest accrual.
        if timing == "in_advance" and row_num == 1:
            interest = Decimal("0")
        else:
            interest = balance * rate_periodic

        principal_portion = total_payment - interest
        balance = balance - principal_portion

        period_start = _add_months(begin, row_num - 1)
        period_end = _add_months(begin, row_num) - timedelta(days=1)
        payment_date = period_start if timing == "in_advance" else period_end

        rows.append(
            {
                "instalment": row_num,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "payment_date": payment_date.isoformat(),
                "opening": _q(opening),
                "interest": _q(interest),
                "payment": _q(total_payment),
                "closing": _q(balance),
                # Unrounded internals retained for FY/split summation.
                "_interest_raw": interest,
                "_payment_raw": total_payment,
                "_closing_raw": balance,
                "_start_date": period_start,
            }
        )

    total_interest = sum((r["_interest_raw"] for r in rows), Decimal("0"))
    total_payments = sum((r["_payment_raw"] for r in rows), Decimal("0"))
    final_balance = rows[-1]["_closing_raw"] if rows else principal

    fy_interest = _fy_interest_map(rows, fy_end_month)
    fy_position = _fy_position_map(rows, principal, fy_end_month)

    advisory_notes = [
        "The residual (rate_precision_residual) is a stated-rate artefact; it "
        "is reported, never forced to zero.",
        "The lender's total amount repayable governs; a non-zero residual "
        "reflects the stated rate's display precision.",
        "contract_form affects GST and title treatment, not the amortisation.",
        "Date convention: period_start = begin_date + k months; period_end = "
        "next period_start minus one day; payment_date = period_start for "
        "in_advance, period_end for in_arrears. LodgeiT labels rows by period "
        "month only.",
    ]

    result = {
        "rows": [_public_row(r) for r in rows],
        "totals": {
            "interest": _q(total_interest),
            "payments": _q(total_payments),
        },
        "final_balance": _q(final_balance),
        "rate_precision_residual": _q(final_balance),
        "fy_interest": fy_interest,
        "fy_position": fy_position,
        "manifest": {
            "calculator": CALCULATOR_URN,
            "engine_version": ENGINE_VERSION,
            "accrual_basis": ACCRUAL_BASIS,
        },
        "advisory": {
            "figure_type": "amortisation_schedule",
            "notes": advisory_notes,
        },
    }
    return result


def _public_row(row: dict) -> dict:
    """Strip the private unrounded helper keys from an output row."""
    return {k: v for k, v in row.items() if not k.startswith("_")}


def _fy_end_date(fy_year: int, fy_end_month: int) -> date:
    """Last day of the FY that ends in the given calendar year/month."""
    last_day = calendar.monthrange(fy_year, fy_end_month)[1]
    return date(fy_year, fy_end_month, last_day)


def _fy_start_date(fy_year: int, fy_end_month: int) -> date:
    """First day of the FY that ends in the given calendar year/month."""
    start_month = (fy_end_month % 12) + 1
    start_year = fy_year - 1 if fy_end_month != 12 else fy_year
    return date(start_year, start_month, 1)


def _fy_interest_map(rows: list[dict], fy_end_month: int) -> dict:
    """Sum interest per financial year, keyed by FY-end calendar year."""
    buckets: dict[int, Decimal] = {}
    for row in rows:
        row_date: date = row["_start_date"]
        # FY-end year: if the row month is after the FY-end month, it belongs
        # to the FY ending next calendar year; otherwise this calendar year.
        if row_date.month > fy_end_month:
            fy_year = row_date.year + 1
        else:
            fy_year = row_date.year
        buckets[fy_year] = buckets.get(fy_year, Decimal("0")) + row["_interest_raw"]
    return {str(year): _q(total) for year, total in sorted(buckets.items())}


def _fy_position_map(rows: list[dict], principal: Decimal, fy_end_month: int) -> dict:
    """Liability split at each FY-end balance date crossed by the schedule."""
    if not rows:
        return {}

    # Distinct FY-end dates from the first row up to the penultimate row: a
    # split is meaningful only when instalments remain after the balance date.
    fy_end_years: list[int] = []
    for row in rows:
        row_date: date = row["_start_date"]
        fy_year = row_date.year + 1 if row_date.month > fy_end_month else row_date.year
        if fy_year not in fy_end_years:
            fy_end_years.append(fy_year)

    positions: dict[str, dict] = {}
    for fy_year in fy_end_years:
        balance_date = _fy_end_date(fy_year, fy_end_month)

        # Principal outstanding = closing balance of the last row on/before
        # the balance date.
        principal_balance = principal
        any_after = False
        for row in rows:
            if row["_start_date"] <= balance_date:
                principal_balance = row["_closing_raw"]
            else:
                any_after = True
        if not any_after:
            # No instalments remain after this FY-end; no split to present.
            continue

        current_gross = Decimal("0")
        current_unexpired = Decimal("0")
        non_current_gross = Decimal("0")
        non_current_unexpired = Decimal("0")

        for row in rows:
            row_date = row["_start_date"]
            if row_date > balance_date:
                months_out = (row_date.year - balance_date.year) * 12 + (
                    row_date.month - balance_date.month
                )
                if months_out <= 12:
                    current_gross += row["_payment_raw"]
                    current_unexpired += row["_interest_raw"]
                else:
                    non_current_gross += row["_payment_raw"]
                    non_current_unexpired += row["_interest_raw"]

        current_net = current_gross - current_unexpired
        non_current_net = non_current_gross - non_current_unexpired

        positions[balance_date.isoformat()] = {
            "principal": _q(principal_balance),
            "current_gross": _q(current_gross),
            "current_unexpired": _q(current_unexpired),
            "current_net": _q(current_net),
            "non_current_gross": _q(non_current_gross),
            "non_current_unexpired": _q(non_current_unexpired),
            "non_current_net": _q(non_current_net),
        }
    return positions
