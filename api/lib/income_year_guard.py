"""Income-year ↔ period-URI consistency guard for period-scoped calculators.

D94 (Fable wire-repro 2026-11-21). The Div 7A engine reads its inputs from two
independent surfaces that nothing cross-checked:

* the **period URI** (``urn:sbrm:period:div7a:fyYYYY``) — the engine's
  ``AU_BenchmarkRate.lookup`` resolves the §109N(2) benchmark rate from it;
* the **body's** ``income_year_start_date`` — the engine's ``enclose()`` turns
  it into ``period_start``/``period_end``, which drive the §109E(6) remaining
  term and the canon-620 interest-day window.

Nothing tied the two together, so a request could carry the FY2026 path and a
2024-25 body and return HTTP 200 mixing the FY2026 rate with the FY2025
remaining term and accrual days.

This module is the gateway-side cross-check. The expected start date is
**derived** from the period URI (``fyYYYY`` is the income year ending 30 June
``YYYY``, so it starts 1 July ``YYYY-1``) — never a hard-coded table, so a
newly ratified period URN needs no guard update.

D95 (Fable wire-repro 2026-11-21) is the same class on the other body field:
the engine filters ``repayments`` to the income year and silently drops the
rest, so a repayment dated ``2023-12-31`` in an FY2025 request produced a full
shortfall and a false §109E(1) deemed dividend with no refusal and no echo.
``repayment_outside_income_year_errors`` refuses every such date, from the same
derived bounds.

The calculator covers standard 1 July – 30 June Australian income years only.
That is a scope fact, not a parsing convenience: a mid-year start has no
statutory meaning here (the engine's ``enclose()`` would silently snap it back
to 1 July, discarding what the caller asked for).
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date, datetime

# A period URN that names a financial year: urn:sbrm:period:<calc>:fyYYYY.
# Non-FY period shapes (e.g. urn:sbrm:period:hp:unscoped) carry no income year,
# so the guard has nothing to assert and stays out of the way.
_PERIOD_FY_RE = re.compile(r"^urn:sbrm:period:[a-z0-9_-]+:fy(\d{4})$")

# The two formats the Div 7A field declares (and the engine's _parse_date
# accepts): ISO YYYY-MM-DD and AU dd/mm/yyyy.
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y")

REFUSAL_INCOME_YEAR_PERIOD_MISMATCH = "income_year_period_mismatch"

# D95 (Fable wire-repro 2026-11-21): a repayment dated outside the period's
# income year. One slug for both faults (outside-the-year, and a date in no
# accepted format): the caller's remedy is the same — put a date from this
# income year, in a format this calculator reads, in that slot — and the msg
# says which. One slug keeps the refusal class stable for integrators.
REFUSAL_REPAYMENT_OUTSIDE_INCOME_YEAR = "repayment_outside_income_year"

FIELD = "income_year_start_date"
REPAYMENTS_FIELD = "repayments"


def parse_iso_or_au_date(value: object) -> date | None:
    """Parse the declared formats; ``None`` when the value is neither."""
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            # strptime keeps the accepted set exactly the engine's own
            # (``jurisdiction_au.div7a_au._parse_date``), including its
            # tolerance of single-digit months/days ("1/7/2024", "2024-7-1").
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def expected_income_year_start(period_uri: str) -> date | None:
    """1 July of the income year named by an ``...:fyYYYY`` period URI.

    ``urn:sbrm:period:div7a:fy2026`` → ``date(2025, 7, 1)``. Returns ``None``
    when the URI does not name a financial year.
    """
    match = _PERIOD_FY_RE.match(period_uri)
    if match is None:
        return None
    return date(int(match.group(1)) - 1, 7, 1)


def expected_income_year_bounds(period_uri: str) -> tuple[date, date] | None:
    """``(1 July, 30 June)`` of the income year named by an ``...:fyYYYY``
    period URI, or ``None`` when the URI names no financial year.

    Both bounds are inclusive: FY2025 is 2024-07-01 through 2025-06-30, and a
    payment made on either boundary day is inside the year.
    """
    start = expected_income_year_start(period_uri)
    if start is None:
        return None
    return start, date(start.year + 1, 6, 30)


def repayment_outside_income_year_errors(
    period_uri: str, repayment_dates: Sequence[object]
) -> list[dict]:
    """Standard-shape 422 entries for every repayment dated outside the
    period's income year.

    D95 (Fable wire-repro 2026-11-21). The engine aggregates repayments over
    the income year and silently drops the rest: a repayment dated
    ``2023-12-31`` in an FY2025 request vanished from ``total_repayments`` and
    the full statutory MYR came back as the §109E(1) deemed dividend. Nothing
    refused it and nothing echoed the drop, so a mistyped year read as a real
    shortfall.

    Empty list = nothing to refuse (all in-year, or the period names no income
    year, in which case the guard has nothing to assert). Otherwise one entry
    per offending repayment, in input order, so a caller sees every bad date in
    one response rather than one per round trip.

    A value in neither declared format is refused here too: the engine's
    ``_parse_date`` would have raised on it, but only after the period's own
    arithmetic was already in flight, and the caller would have had to infer
    which repayment was at fault from a bare message.
    """
    bounds = expected_income_year_bounds(period_uri)
    if bounds is None:
        return []
    start, end = bounds
    start_iso = start.isoformat()
    end_iso = end.isoformat()

    errors: list[dict] = []
    for index, raw in enumerate(repayment_dates):
        parsed = parse_iso_or_au_date(raw)
        loc = ["body", REPAYMENTS_FIELD, index, "date"]

        if parsed is None:
            errors.append(
                {
                    "loc": loc,
                    "msg": (
                        f"{REPAYMENTS_FIELD}[{index}].date={raw!r} is not a "
                        f"date this calculator accepts: the accepted formats "
                        f"are ISO YYYY-MM-DD and AU dd/mm/yyyy, so this value "
                        f"cannot be placed in the income year {start_iso} to "
                        f"{end_iso} named by the period {period_uri}."
                    ),
                    "type": REFUSAL_REPAYMENT_OUTSIDE_INCOME_YEAR,
                }
            )
            continue

        if start <= parsed <= end:
            continue

        errors.append(
            {
                "loc": loc,
                "msg": (
                    f"{REPAYMENTS_FIELD}[{index}].date={raw!r} is outside the "
                    f"income year {start_iso} to {end_iso} named by the "
                    f"period {period_uri}. This calculator aggregates "
                    f"repayments over that income year only, so a repayment "
                    f"dated outside it would be dropped from the calculation "
                    f"while still sitting on the caller's ledger — reporting "
                    f"a shortfall and a §109E(1) deemed dividend that the "
                    f"repayment had in fact met. Send ISO YYYY-MM-DD or AU "
                    f"dd/mm/yyyy, inside {start_iso} to {end_iso}."
                ),
                "type": REFUSAL_REPAYMENT_OUTSIDE_INCOME_YEAR,
            }
        )
    return errors


def income_year_period_error(period_uri: str, value: object) -> dict | None:
    """Build the standard-shape 422 line item, or ``None`` when consistent.

    Standard shape per the D73 convention (``loc`` / ``msg`` / ``type``), the
    same shape the hp route emits for its typed 422s and the shape FastAPI's
    own body-validation 422s take, so a caller sees one convention on every
    refusal this surface produces.
    """
    expected = expected_income_year_start(period_uri)
    if expected is None:
        return None

    parsed = parse_iso_or_au_date(value)
    if parsed == expected:
        return None

    bounds = expected_income_year_bounds(period_uri)
    assert bounds is not None  # expected_income_year_start already matched
    expected_iso = expected.isoformat()
    expected_au = expected.strftime("%d/%m/%Y")
    end_iso = bounds[1].isoformat()

    if parsed is None:
        lead = (
            f"income_year_start_date={value!r} is not a date this calculator "
            f"accepts (ISO YYYY-MM-DD or AU dd/mm/yyyy)."
        )
    else:
        lead = (
            f"income_year_start_date={value!r} is not the start of the income "
            f"year named by the period."
        )

    return {
        "loc": ["body", FIELD],
        "msg": (
            f"{lead} The period {period_uri} is the Australian income year "
            f"{expected_iso} to {end_iso}, so income_year_start_date must be "
            f"{expected_iso} (ISO) or {expected_au} (AU). This calculator "
            f"covers standard 1 July to 30 June income years only: the period "
            f"URI fixes the §109N(2) benchmark rate while "
            f"income_year_start_date fixes the §109E(6) remaining term and "
            f"the interest-day window, so any other date would compute one "
            f"income year's rate against another income year's arithmetic."
        ),
        "type": REFUSAL_INCOME_YEAR_PERIOD_MISMATCH,
    }


__all__ = [
    "FIELD",
    "REPAYMENTS_FIELD",
    "REFUSAL_INCOME_YEAR_PERIOD_MISMATCH",
    "REFUSAL_REPAYMENT_OUTSIDE_INCOME_YEAR",
    "expected_income_year_bounds",
    "expected_income_year_start",
    "income_year_period_error",
    "parse_iso_or_au_date",
    "repayment_outside_income_year_errors",
]
