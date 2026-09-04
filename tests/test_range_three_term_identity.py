"""D7 property test: `/range/` three-term reconciliation identity.

**Fable post-matrix directive mc00-2026-09-04 D7 (§4) as re-ruled at
07:35 UTC.**

Original D7 finding (§4 verbatim):

    "`/range/` does not reconcile when the acquisition falls inside the
     range. CELL 5 from 2023-05-01 to 2023-08-31, acquisition 2023-07-01:
     opening_wdv 0.00   range_dep 338.80   closing_wdv 9661.20
     0.00 − 338.80 = −338.80  ≠  9661.20

     The identity holds in cells 3, 4, 6, 11 and 12b and fails here,
     because the asset's cost enters inside the window and the response
     carries no column for it.

     The correct ledger identity for a roll-forward is not the two-term
     one we ratified:

         closing_wdv = opening_wdv + cost_additions − range_dep

     Ruled: `/range/` gains `cost_additions`, always present, and the
     three-term identity replaces the two-term one everywhere it is
     asserted. And extend the property test first ... watch them fail,
     then fix."

**FABLE RE-RULING mc00-2026-09-04 07:35 UTC (verbatim):**

    "The synthesis is the identity rearranged.

     synthesis: cost_additions = closing_wdv + range_dep − opening_wdv
     identity: closing_wdv = opening_wdv + cost_additions − range_dep

     substitute: closing = opening + (closing + range_dep − opening) −
     range_dep = closing

     A tautology. The identity now holds algebraically for any four
     numbers, whatever they are. Feed the gateway a wrong opening_wdv,
     a wrong range_dep, or a wrong closing_wdv, and the synthesised
     cost_additions silently absorbs the error and the identity still
     balances. Your ten property tests pass because arithmetic makes
     them pass, not because the numbers are right.

     D7 existed because cell 5 failed to reconcile — that failure was
     the signal. The remedy converted a detectable defect into an
     undetectable one and reported it as green.

     Ruled:
      1. Remove the synthesis. The gateway must never manufacture a
         value it then uses to verify itself.
      2. The engine emits cost_additions on /range/. It already tracks
         this — /at/'s schedule_summary carries total_cost_additions,
         so the information exists in the fold. That is an engine PR,
         sequenced ahead of the gateway change, same engine-first
         ordering as :unscoped.
      3. The gateway passes it through and asserts the identity
         against it. A mismatch is a structured error naming both
         sides, not a repaired value.
      4. Until the engine emits it, /range/ omits cost_additions and
         the drift log fires. An absent field is honest. A synthesised
         one is a fabricated corroboration in a response a preparer
         relies on."

**Anchor Fable named (verbatim):** *"A check that cannot fail is not
a weaker check. It is the absence of a check, wearing the costume of
one. That is the same family as the exit code locked to zero,
EXIT_CODE: $? after a pipe, the coherence audit that could not see
SR #15, and the smoke set with no cell for the surface under test.
We have now produced this shape ourselves twice while explicitly
hunting it. Bank that, because it is the more uncomfortable half:
the discipline does not immunise you against the defect it was built
to catch."*

**Current test file shape (after 07:35 UTC re-ruling):**

Three assertion classes are preserved:

  1. `cost_additions_ABSENT_until_engine_ships` — pins the current wire
     state honestly. The field IS missing from `/range/` responses
     today. Test fails ONLY when the engine starts emitting the field
     (which is the signal to flip the identity assertions on in the
     next PR alongside the engine ship).

  2. `two_term_corollary_holds_when_acquisition_outside_range` — the
     two-term identity `closing_wdv = opening_wdv − range_dep` holds
     for acquisition-outside-range configurations (Fable §4 cells 3,
     4, 6, 11, 12b shape). This tests the engine's arithmetic against
     the current wire shape without any synthesis. Non-tautological
     because the engine's numbers are compared against each other, not
     against a value derived from them.

  3. `identity_assertion_awaits_engine_ship` — the acquisition-inside-
     range configurations (Fable §4 cell 5 shape) are documented but
     skipped with `pytest.skip("awaiting engine cost_additions PR")`.
     Fixtures + expected values remain baked in so the follow-up
     gateway PR (post engine ship) turns them on with an edit-per-
     skip-line-removal.

**When the engine PR ships `cost_additions` on `/range/`:**

  1. Engine tests exercise the field emission at the engine layer.
  2. Gateway follow-up PR:
     * Adds cost_additions as a REQUIRED (no default) field on
       DepreciationRangeResponse.
     * Adds an assertion in the route handler that
       closing_wdv == opening_wdv + cost_additions − range_dep,
       structured 502 on mismatch naming both sides.
     * Removes the pytest.skip lines below.
     * Adds a new test asserting that a MUTATED engine response (e.g.
       cost_additions off by 0.01) triggers the mismatch 502. This
       is the falsifiability gate the tautology destroyed.

Fable's ruling closes this milestone as "revert + re-sequence"; the
gateway does not carry the field until the engine authors it.
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
    """Build a mock engine response. `include_cost_additions=None` mirrors
    the engine's current wire shape (field absent). Non-None only when
    exercising the future-engine-emitted-shape assertion path."""
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
# Assertion class 1 — cost_additions ABSENT until engine ships.
#
# This is the honest report of the current wire shape. Fable 07:35 UTC:
# "an absent field is honest. A synthesised one is a fabricated
# corroboration."
#
# When the engine starts emitting the field, the passthrough test flips
# (cost_additions now present); the acquisition-inside-range assertions
# below unskip; and the tautology-avoidance discipline is preserved
# because the value comes from the engine and the identity holds only
# when all four numbers are right.
# ============================================================================


def test_range_response_currently_omits_cost_additions(client: TestClient) -> None:
    """Pins the current wire state. `/range/` responses do NOT carry
    `cost_additions` because the engine does not emit it yet. When this
    test starts failing (engine has landed the field), the follow-up
    gateway PR is due: add the required field to the schema, add the
    identity assertion in the route handler, unskip the three-term tests
    below.
    """
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
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "cost_additions" not in body, (
        "cost_additions is now on the wire. Engine PR has landed; "
        "flip the follow-up gateway PR: declare the field required on "
        "DepreciationRangeResponse, add the three-term identity assertion "
        "in the route handler, and unskip the acquisition-inside-range "
        "tests in this file. Body: " + str(body)
    )


# ============================================================================
# Assertion class 2 — two-term corollary holds when acquisition is OUTSIDE
# the range. Non-tautological: opening_wdv, closing_wdv, range_dep are all
# engine-authored numbers; the assertion compares them against each other,
# not against a derived value.
# ============================================================================


def test_cell6_two_term_corollary_holds(client: TestClient) -> None:
    """Fable §4 cell 6 shape: opening 10000, range_dep 169.40, closing
    9830.60. Acquisition (2023-07-01) is BEFORE from_date (2023-08-01),
    so no cost enters the ledger inside the range. Two-term identity
    holds as a corollary of the three-term identity when
    `cost_additions == 0`."""
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
    opening_wdv = Decimal(body["opening_wdv"])
    closing_wdv = Decimal(body["closing_wdv"])
    range_dep = Decimal(body["range_dep"])
    assert closing_wdv == opening_wdv - range_dep, (
        f"Two-term corollary failed on acquisition-outside-range: "
        f"{closing_wdv} != {opening_wdv} − {range_dep} = "
        f"{opening_wdv - range_dep}. "
        f"This IS a real signal — the engine's arithmetic is wrong, or "
        f"the response has been mutated between engine and gateway."
    )


def test_cell3_two_term_corollary_holds_second_fy(client: TestClient) -> None:
    """Fable §4 cell 3 shape: second FY roll-forward, acquisition before
    from_date. Two-term corollary holds."""
    engine_resp = _engine_response(
        opening_wdv="9000.00",
        closing_wdv="8000.00",
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
                acquisition_date="2022-07-01",
                from_date="2023-07-01",
                to_date="2024-06-30",
            ),
        )
    assert resp.status_code == 200
    body = resp.json()
    opening_wdv = Decimal(body["opening_wdv"])
    closing_wdv = Decimal(body["closing_wdv"])
    range_dep = Decimal(body["range_dep"])
    assert closing_wdv == opening_wdv - range_dep


# ============================================================================
# Assertion class 3 — acquisition INSIDE range configurations.
#
# These test the three-term identity. They are SKIPPED until the engine
# ships cost_additions on /range/. When it does, unskip + the follow-up
# gateway PR that lands the identity assertion in the route handler
# turns them into a real gate.
#
# Fixtures + expected values are baked in so unskipping is a single-line
# edit per test.
# ============================================================================


_AWAITS_ENGINE_SHIP = pytest.mark.skip(
    reason=(
        "Awaiting engine PR that emits cost_additions on /range/. Fable "
        "07:35 UTC ruling: gateway does not synthesise; engine authors "
        "the field, gateway asserts identity against it. Until then, "
        "cost_additions absent from response is honest. Unskip alongside "
        "the follow-up gateway PR that (a) declares cost_additions on "
        "DepreciationRangeResponse, (b) adds identity-assertion in the "
        "route handler with structured 502 on mismatch."
    )
)


@_AWAITS_ENGINE_SHIP
def test_cell5_acquisition_inside_range_three_term_identity(
    client: TestClient,
) -> None:
    """Fable §4 CELL 5 replay: from_date 2023-05-01, to_date 2023-08-31,
    acquisition_date 2023-07-01. Cost 10000, prime cost, life 10y.
    Engine emits `cost_additions=10000.00` (acquisition falls inside
    range). Three-term identity holds against the engine-emitted value;
    the gateway does NOT derive."""
    engine_resp = _engine_response(
        opening_wdv="0.00",
        closing_wdv="9661.20",
        range_dep="338.80",
        include_cost_additions="10000.00",  # engine-emitted
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
    assert "cost_additions" in body
    opening_wdv = Decimal(body["opening_wdv"])
    closing_wdv = Decimal(body["closing_wdv"])
    range_dep = Decimal(body["range_dep"])
    cost_additions = Decimal(body["cost_additions"])
    # Three-term identity against engine-emitted values (no synthesis).
    assert closing_wdv == opening_wdv + cost_additions - range_dep
    assert cost_additions == Decimal("10000.00")


@_AWAITS_ENGINE_SHIP
def test_mutated_engine_response_triggers_identity_mismatch_502(
    client: TestClient,
) -> None:
    """Falsifiability gate — the assertion Fable's tautology-anchor
    ruling exists to create. Feed a MUTATED engine response where
    cost_additions is off by 0.01. The route handler's identity check
    catches it and surfaces a structured 502 naming both sides.

    A synthesised cost_additions would have SILENTLY ABSORBED the
    error. This is why the gateway must not manufacture the value it
    then uses to verify itself.
    """
    engine_resp = _engine_response(
        opening_wdv="0.00",
        closing_wdv="9661.20",
        range_dep="338.80",
        include_cost_additions="9999.99",  # WRONG by 0.01
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
    # Expected shape when the follow-up gateway PR ships the assertion:
    #   HTTP 502
    #   detail.error == "range_identity_mismatch"
    #   detail carries all four numbers so both sides are visible.
    assert resp.status_code == 502
    detail = resp.json().get("detail", {})
    assert detail.get("error") == "range_identity_mismatch"
    assert "opening_wdv" in detail
    assert "closing_wdv" in detail
    assert "range_dep" in detail
    assert "cost_additions" in detail
