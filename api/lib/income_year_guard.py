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

The calculator covers standard 1 July – 30 June Australian income years only.
That is a scope fact, not a parsing convenience: a mid-year start has no
statutory meaning here (the engine's ``enclose()`` would silently snap it back
to 1 July, discarding what the caller asked for).
"""
from __future__ import annotations

import re
from datetime import date, datetime

# A period URN that names a financial year: urn:sbrm:period:<calc>:fyYYYY.
# Non-FY period shapes (e.g. urn:sbrm:period:hp:unscoped) carry no income year,
# so the guard has nothing to assert and stays out of the way.
_PERIOD_FY_RE = re.compile(r"^urn:sbrm:period:[a-z0-9_-]+:fy(\d{4})$")

# The two formats the Div 7A field declares (and the engine's _parse_date
# accepts): ISO YYYY-MM-DD and AU dd/mm/yyyy.
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y")

REFUSAL_INCOME_YEAR_PERIOD_MISMATCH = "income_year_period_mismatch"

FIELD = "income_year_start_date"


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

    expected_iso = expected.isoformat()
    expected_au = expected.strftime("%d/%m/%Y")
    end_iso = date(expected.year + 1, 6, 30).isoformat()

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
    "REFUSAL_INCOME_YEAR_PERIOD_MISMATCH",
    "expected_income_year_start",
    "income_year_period_error",
    "parse_iso_or_au_date",
]
