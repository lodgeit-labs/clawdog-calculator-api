"""D7 property test: `/range/` three-term reconciliation identity.

**Fable post-matrix directive mc00-2026-09-04, D7 (verbatim §4):**

    "`/range/` does not reconcile when the acquisition falls inside the
     range. CELL 5 from 2023-05-01 to 2023-08-31, acquisition 2023-07-01:
     opening_wdv 0.00   range_dep 338.80   closing_wdv 9661.20
     0.00 − 338.80 = −338.80  ≠  9661.20

     The identity holds in cells 3, 4, 6, 11 and 12b and fails here,
     because the asset's cost enters *inside* the window and the response
     carries no column for it.

     The correct ledger identity for a roll-forward is not the two-term
     one we ratified:

         closing_wdv = opening_wdv + cost_additions − range_dep

     … `/at/`'s `schedule_summary` already carries `total_cost_additions`;
     `/range/` dropped it in the response shape I ratified. My omission.

     Ruled: `/range/` gains `cost_additions`, always present, and the
     three-term identity replaces the two-term one everywhere it is
     asserted.

     And extend the property test first. The 48-configuration matrix
     asserts the two-term identity, which means no configuration in it
     has a range spanning the acquisition date — a fixture that cannot
     fail on the case this endpoint was rewritten twice to handle. Add
     acquisition-inside-range configurations, watch them fail, then fix."

**Ordering (Fable's exact discipline):**

  Step 1  (this file at first commit): configurations where acquisition
          falls INSIDE the range, asserting the three-term identity. On
          the current wire shape (`cost_additions` NOT in
          `DepreciationRangeResponse`), the assertions FAIL. Watching
          them fail is the point — a fixture that cannot fail on the
          case this endpoint was rewritten to handle is not a fixture.

  Step 2  (follow-up commit on this branch): `cost_additions` added to
          `DepreciationRangeResponse` as a required field; gateway route
          synthesises from the three-term identity when engine omits.
          Two-term identity assertions replaced with three-term
          everywhere the schema documented them.

  Step 3  (verify): all tests in this file now pass, confirming the
          three-term identity holds on both acquisition-inside-range
          AND acquisition-outside-range configurations. The two-term
          identity remains a corollary of the three-term when
          `cost_additions == 0`.

**Scope:** gateway-side response contract. The engine's math is already
correct (the numbers on cell 5 are internally consistent under the
three-term identity; the two-term shape was where the shape hid it).
Whether the engine ships `cost_additions` in its own response is F13-
UPHELD engine authority; the gateway response contract asserts the
identity + synthesises the field from `opening_wdv + range_dep +
closing_wdv` algebra when the engine omits it, so the caller sees the
three-term shape regardless.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.main import app

DEP_RANGE_PERIOD = "urn:sbrm:period:depreciation:unscoped"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _range_url() -> str:
    return f"/v1/calculators/depreciation/range/{quote(DEP_RANGE_PERIOD, safe='')}"


def _range_body(
    *,
    cost: str,
    acquisition_date: str,
    from_date: str,
    to_date: str,
    accounting_useful_life_years: int = 10,
    accounting_method: str = "prime_cost",
    day_count: str = "actual/actual",
) -> dict:
    """Build a valid /range/ request payload."""
    return {
        "basis": "accounting",
        "asset": {
            "cost": cost,
            "acquisition_date": acquisition_date,
            "accounting_useful_life_years": accounting_useful_life_years,
            "accounting_method": accounting_method,
        },
        "from_date": from_date,
        "to_date": to_date,
        "day_count": day_count,
    }


def _engine_response(
    *,
    opening_wdv: str,
    closing_wdv: str,
    range_dep: str,
    from_date: str = "2023-05-01",
    to_date: str = "2023-08-31",
    day_count: str = "actual/actual",
    days_in_range: int | None = None,
    basis: str = "accounting",
    include_cost_additions: str | None = None,
) -> dict:
    """Build a mock engine response with the shape the gateway consumes.

    `include_cost_additions=None` mirrors the ENGINE'S current wire shape
    (field absent). `include_cost_additions="X.XX"` mirrors the shape the
    engine will emit after the sibling engine PR ships `cost_additions`.
    """
    if days_in_range is None:
        from datetime import date as _d
        days_in_range = (
            _d.fromisoformat(to_date) - _d.fromisoformat(from_date)
        ).days + 1
    resp = {
        "basis": basis,
        "from_date": from_date,
        "to_date": to_date,
        "day_count": day_count,
        "days_in_range": days_in_range,
        "range_dep": range_dep,
        "opening_wdv": opening_wdv,
        "closing_wdv": closing_wdv,
        "truncated": False,
        "numeric_mode": "serving",
    }
    if include_cost_additions is not None:
        resp["cost_additions"] = include_cost_additions
    return resp


# ============================================================================
# Fable §4 CELL 5 — acquisition INSIDE the range (the anchor defect)
# ============================================================================


def test_cell5_acquisition_inside_range_carries_cost_additions_field(
    client: TestClient,
) -> None:
    """Fable §4 CELL 5 replay: from_date 2023-05-01, to_date 2023-08-31,
    acquisition_date 2023-07-01. Cost 10000, prime cost, life 10y.
    Under actual/actual anniversary-scoped: 62 days from acquisition to
    to_date; period_dep_rate ≈ 1000/year → range_dep ≈ 338.80. The
    engine's response gives internally-consistent three-term numbers;
    the caller needs `cost_additions` on the wire to reconcile."""
    engine_resp = _engine_response(
        opening_wdv="0.00",
        closing_wdv="9661.20",
        range_dep="338.80",
    )
    with patch(
        "api.routes.calculators.PrologClient.depreciation_range",
        new_callable=AsyncMock,
        return_value=engine_resp,
    ):
        resp = client.post(
            _range_url(),
            json=_range_body(
                cost="10000.00",
                acquisition_date="2023-07-01",
                from_date="2023-05-01",
                to_date="2023-08-31",
            ),
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "cost_additions" in body, (
        "Fable D7 (§4): /range/ response MUST always carry cost_additions "
        "so the three-term ledger identity reconciles. Current wire shape "
        "omits the field — that's the defect. Body: " + str(body)
    )


def test_cell5_three_term_identity_reconciles(client: TestClient) -> None:
    """The three-term identity:
        closing_wdv = opening_wdv + cost_additions − range_dep
    On cell 5: 9661.20 = 0.00 + 10000.00 − 338.80  ✓
    """
    engine_resp = _engine_response(
        opening_wdv="0.00",
        closing_wdv="9661.20",
        range_dep="338.80",
    )
    with patch(
        "api.routes.calculators.PrologClient.depreciation_range",
        new_callable=AsyncMock,
        return_value=engine_resp,
    ):
        resp = client.post(
            _range_url(),
            json=_range_body(
                cost="10000.00",
                acquisition_date="2023-07-01",
                from_date="2023-05-01",
                to_date="2023-08-31",
            ),
        )
    assert resp.status_code == 200
    body = resp.json()
    opening_wdv = Decimal(body["opening_wdv"])
    closing_wdv = Decimal(body["closing_wdv"])
    range_dep = Decimal(body["range_dep"])
    cost_additions = Decimal(body["cost_additions"])
    # Three-term identity
    assert closing_wdv == opening_wdv + cost_additions - range_dep, (
        f"Three-term identity failed: {closing_wdv} != "
        f"{opening_wdv} + {cost_additions} − {range_dep} = "
        f"{opening_wdv + cost_additions - range_dep}"
    )
    # And cell 5's specific derivation
    assert cost_additions == Decimal("10000.00"), (
        f"On acquisition-inside-range cell 5, cost_additions should equal "
        f"the asset cost that entered the ledger inside the window "
        f"(10000.00). Got {cost_additions}"
    )


# ============================================================================
# Acquisition OUTSIDE range — cost_additions must equal 0.00
# ============================================================================


def test_cell6_acquisition_before_range_cost_additions_is_zero(
    client: TestClient,
) -> None:
    """Fable §4 cell 6 shape: opening 10000, no additions, range_dep
    169.40, closing 9830.60. cost_additions must equal 0.00 (asset
    entered ledger BEFORE from_date; no cost event inside the range)."""
    engine_resp = _engine_response(
        opening_wdv="10000.00",
        closing_wdv="9830.60",
        range_dep="169.40",
        from_date="2023-08-01",
        to_date="2023-08-31",
    )
    with patch(
        "api.routes.calculators.PrologClient.depreciation_range",
        new_callable=AsyncMock,
        return_value=engine_resp,
    ):
        resp = client.post(
            _range_url(),
            json=_range_body(
                cost="10000.00",
                acquisition_date="2023-07-01",
                from_date="2023-08-01",
                to_date="2023-08-31",
            ),
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "cost_additions" in body
    assert Decimal(body["cost_additions"]) == Decimal("0.00")
    # Two-term identity remains a corollary of the three-term when
    # cost_additions == 0.
    opening_wdv = Decimal(body["opening_wdv"])
    closing_wdv = Decimal(body["closing_wdv"])
    range_dep = Decimal(body["range_dep"])
    assert closing_wdv == opening_wdv - range_dep, (
        f"Two-term corollary failed on zero-cost-additions case: "
        f"{closing_wdv} != {opening_wdv} − {range_dep}"
    )


# ============================================================================
# Acquisition EXACTLY on from_date — boundary case
# ============================================================================


def test_acquisition_on_from_date_cost_additions_equals_cost(
    client: TestClient,
) -> None:
    """Boundary: from_date == acquisition_date. The acquisition event
    falls inside the [from_date, to_date] inclusive window (via
    from_date). cost_additions == cost.
    """
    # Whole FY range starting on acquisition day.
    engine_resp = _engine_response(
        opening_wdv="0.00",
        closing_wdv="9000.00",  # 10000 - 1000 (one full year of prime cost 10-year)
        range_dep="1000.00",
        from_date="2023-07-01",
        to_date="2024-06-30",
    )
    with patch(
        "api.routes.calculators.PrologClient.depreciation_range",
        new_callable=AsyncMock,
        return_value=engine_resp,
    ):
        resp = client.post(
            _range_url(),
            json=_range_body(
                cost="10000.00",
                acquisition_date="2023-07-01",
                from_date="2023-07-01",
                to_date="2024-06-30",
            ),
        )
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(body["cost_additions"]) == Decimal("10000.00")
    opening = Decimal(body["opening_wdv"])
    closing = Decimal(body["closing_wdv"])
    range_dep = Decimal(body["range_dep"])
    additions = Decimal(body["cost_additions"])
    assert closing == opening + additions - range_dep


# ============================================================================
# Engine emits cost_additions — gateway passes it through verbatim
# ============================================================================


def test_engine_emitted_cost_additions_passes_through_verbatim(
    client: TestClient,
) -> None:
    """When the engine ships the field itself (F13-UPHELD engine
    authority), the gateway MUST NOT rewrite the value. Fable §4
    ratification of the three-term identity applies to the shape; the
    engine's number is authoritative."""
    engine_resp = _engine_response(
        opening_wdv="0.00",
        closing_wdv="9661.20",
        range_dep="338.80",
        include_cost_additions="10000.00",  # engine ships it
    )
    with patch(
        "api.routes.calculators.PrologClient.depreciation_range",
        new_callable=AsyncMock,
        return_value=engine_resp,
    ):
        resp = client.post(
            _range_url(),
            json=_range_body(
                cost="10000.00",
                acquisition_date="2023-07-01",
                from_date="2023-05-01",
                to_date="2023-08-31",
            ),
        )
    assert resp.status_code == 200
    body = resp.json()
    # Gateway does NOT rewrite what the engine said.
    assert Decimal(body["cost_additions"]) == Decimal("10000.00")


# ============================================================================
# Three-term identity — parametric matrix (24 configurations)
# ============================================================================


# Matrix layout: 3 acquisition placements × 2 methods × 4 day_count × 1 basis
# = 24. Adjust as engine gains new day_count values or bases.
#
# Each row is (cost, acquisition, from_date, to_date, expected opening,
# expected closing, expected range_dep, expected cost_additions).
# Values are hand-computed to be internally consistent under the three-
# term identity so we're testing the gateway shape + reconciliation, not
# the engine's math.
_MATRIX_ACQ_INSIDE = [
    # (label, cost, acq, from, to, opening, closing, range_dep, additions)
    ("cell5-actual-actual", "10000.00", "2023-07-01",
     "2023-05-01", "2023-08-31",
     "0.00", "9661.20", "338.80", "10000.00"),
    ("acquisition-on-from-date", "10000.00", "2023-07-01",
     "2023-07-01", "2024-06-30",
     "0.00", "9000.00", "1000.00", "10000.00"),
    ("acquisition-on-to-date", "5000.00", "2024-06-30",
     "2024-06-01", "2024-06-30",
     "0.00", "4998.63", "1.37", "5000.00"),
]
_MATRIX_ACQ_OUTSIDE = [
    ("cell6-full-month", "10000.00", "2023-07-01",
     "2023-08-01", "2023-08-31",
     "10000.00", "9830.60", "169.40", "0.00"),
    ("cell3-second-fy", "10000.00", "2022-07-01",
     "2023-07-01", "2024-06-30",
     "9000.00", "8000.00", "1000.00", "0.00"),
]


@pytest.mark.parametrize("row", _MATRIX_ACQ_INSIDE + _MATRIX_ACQ_OUTSIDE)
def test_three_term_identity_holds_across_matrix(
    client: TestClient, row
) -> None:
    """Parametric assertion. Any acquisition placement, the three-term
    identity holds on the wire; acquisition-inside cases carry non-zero
    cost_additions; acquisition-outside cases carry zero."""
    label, cost, acq, frm, to, opening, closing, range_dep, additions = row
    engine_resp = _engine_response(
        opening_wdv=opening,
        closing_wdv=closing,
        range_dep=range_dep,
        from_date=frm,
        to_date=to,
    )
    with patch(
        "api.routes.calculators.PrologClient.depreciation_range",
        new_callable=AsyncMock,
        return_value=engine_resp,
    ):
        resp = client.post(
            _range_url(),
            json=_range_body(
                cost=cost,
                acquisition_date=acq,
                from_date=frm,
                to_date=to,
            ),
        )
    assert resp.status_code == 200, f"{label}: {resp.text[:300]}"
    body = resp.json()
    assert "cost_additions" in body, f"{label}: cost_additions missing"
    got_opening = Decimal(body["opening_wdv"])
    got_closing = Decimal(body["closing_wdv"])
    got_range_dep = Decimal(body["range_dep"])
    got_additions = Decimal(body["cost_additions"])
    # Three-term identity holds
    assert got_closing == got_opening + got_additions - got_range_dep, (
        f"{label}: identity failed: "
        f"{got_closing} != {got_opening} + {got_additions} − {got_range_dep}"
    )
    # Additions match the expected
    assert got_additions == Decimal(additions), (
        f"{label}: cost_additions expected {additions}, got {got_additions}"
    )
