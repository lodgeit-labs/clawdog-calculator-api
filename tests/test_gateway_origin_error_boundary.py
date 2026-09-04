"""Gateway-origin vs engine-origin error boundary — pinning tests.

**Fable mc00-2026-09-04 05:21 UTC — Amendment-1 boundary guard.**

After D8a Amendment 1 landed, engine-returned 4xx status codes are
partitioned by fault:

  * caller-fault  → same 4xx re-emitted with detail
  * gateway-fault → 502 engine_unavailable (401/403/404/405)
  * rate-limit    → 503 (429)

The 404 → 502 rewrite is correct for a 404 THE ENGINE returns. But the
gateway generates 404s of its own, and they are caller-facing and correct:

  * retired period URN — cell 2's *"period_uri='…:fy2026' is not supported by
    calculator…"* — the message that tells the caller which URN to use instead.
  * unknown calc_uri — the generic route's *"calc_uri=… is not in the Phase 3a
    calculator registry."*

If either of those ever reaches the mapper, Amendment 1 would convert a
correct informative 404 into 502 engine_unavailable and the actionable
detail would disappear.

Fable ruled (verbatim mc00 05:21 UTC):

> *The mapper only sees engine responses today, so this is almost certainly
> safe. "Almost certainly safe" is what cell 2 and cell 13 both were before
> a probe read the body. Add two assertions: a gateway-origin retired-URN
> 404 and an unknown-calc_uri 404 both still return 404 with their original
> detail intact. Cheap, and it pins the boundary between gateway-origin and
> engine-origin errors — which is now a real boundary with different
> behaviour on each side, and nothing currently tests that it holds.*

This file IS that pin. If either assertion ever flips to 502, someone has
routed gateway-origin 404s through the engine-error mapper.

Also asserts the structural boundary at a lower level: the mapper's public
API accepts only PrologEngineUnavailable / PrologCalculationError. If
someone changes the mapper to accept a bare HTTPException or a raw status
code, the type-guard test below breaks.
"""
from __future__ import annotations

from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.main import app

# ============================================================================
# Fixtures — retired URN + unknown calc_uri constants
# ============================================================================

# Fable D5 mc02 2026-09-04: `:fy2026` retired in favour of `:unscoped`. The
# retirement 404 message names `:unscoped` as the replacement — the ONLY
# thing telling a caller what to use instead.
RETIRED_DEP_PERIOD = "urn:sbrm:period:depreciation:fy2026"
LIVE_DEP_PERIOD = "urn:sbrm:period:depreciation:unscoped"

UNKNOWN_CALC_URI = "urn:sbrm:calculator:not-a-real-calculator"
LIVE_FBT_PERIOD = "urn:sbrm:period:fbt:fy2026"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ============================================================================
# Assertion 1 — retired-URN 404 stays a 404 with original detail
# ============================================================================


def test_retired_period_urn_on_depreciation_at_returns_gateway_404(
    client: TestClient,
) -> None:
    """Cell-2 replay: the `:fy2026` retired URN must produce a 404 with a
    message naming `:unscoped` as the replacement. If Amendment 1 ever
    swallows this into 502, the retirement message — the ONLY thing telling
    a caller what to use instead — disappears."""
    resp = client.post(
        f"/v1/calculators/depreciation/at/{quote(RETIRED_DEP_PERIOD, safe='')}",
        json={
            "basis": "accounting",
            "asset": {
                "cost": "5000.00",
                "acquisition_date": "2022-07-01",
                "accounting_useful_life_years": 10,
                "accounting_method": "prime_cost",
            },
            "at_date": "2025-06-30",
        },
    )
    assert resp.status_code == 404, (
        f"Retired-URN 404 was reclassified to {resp.status_code}. Something "
        f"routed gateway-origin 404s through the engine-error mapper "
        f"(Amendment 1 gateway-fault-4xx branch would emit 502). "
        f"Boundary broken. Body: {resp.text[:300]}"
    )
    # Structural: FastAPI wraps HTTPException `detail` under top-level `detail`.
    body = resp.json()
    detail_text = str(body.get("detail", ""))
    assert LIVE_DEP_PERIOD in detail_text, (
        f"Retirement message must name the replacement URN {LIVE_DEP_PERIOD!r} "
        f"so the caller knows what to use. Got: {detail_text!r}"
    )
    assert "fy2026" in detail_text or RETIRED_DEP_PERIOD in detail_text, (
        f"Retirement message must reproduce the retired URN for verbatim "
        f"lookup. Got: {detail_text!r}"
    )


def test_retired_period_urn_on_depreciation_range_returns_gateway_404(
    client: TestClient,
) -> None:
    """Same boundary guard on the sibling `/range/` route. `day_count` is
    required by the `/range/` schema so we supply it — the assertion is
    that even with a fully-valid body the retired URN produces a 404, not
    that the URN check overrides pydantic (it doesn't; pydantic fires first).
    """
    resp = client.post(
        f"/v1/calculators/depreciation/range/{quote(RETIRED_DEP_PERIOD, safe='')}",
        json={
            "basis": "accounting",
            "asset": {
                "cost": "10000.00",
                "acquisition_date": "2023-07-01",
                "accounting_useful_life_years": 10,
                "accounting_method": "prime_cost",
            },
            "from_date": "2023-08-01",
            "to_date": "2024-06-30",
            "day_count": "actual/actual",
        },
    )
    assert resp.status_code == 404, (
        f"Retired-URN 404 on /range/ reclassified to {resp.status_code}. "
        f"Body: {resp.text[:300]}"
    )
    body = resp.json()
    assert LIVE_DEP_PERIOD in str(body.get("detail", ""))


# ============================================================================
# Assertion 2 — unknown-calc_uri 404 on the generic route stays a 404
# ============================================================================


def test_unknown_calc_uri_on_generic_route_returns_gateway_404(
    client: TestClient,
) -> None:
    """The generic `/v1/calculators/{calc_uri}/{period_uri}` route emits a
    404 naming the registered calculator set when the URI is unknown. That
    404 is the caller's only signal that they mis-typed or mis-referenced a
    calculator. If Amendment 1 ever swallows it into 502 the caller cannot
    even tell whether the calculator exists."""
    resp = client.post(
        f"/v1/calculators/{quote(UNKNOWN_CALC_URI, safe='')}/{quote(LIVE_FBT_PERIOD, safe='')}",
        json={"any": "payload"},
    )
    assert resp.status_code == 404, (
        f"Unknown-calc_uri 404 reclassified to {resp.status_code}. "
        f"Body: {resp.text[:300]}"
    )
    body = resp.json()
    detail_text = str(body.get("detail", ""))
    assert UNKNOWN_CALC_URI in detail_text, (
        f"Unknown-calc_uri message must reproduce the requested URI so the "
        f"caller can grep their own code for the typo. Got: {detail_text!r}"
    )


# ============================================================================
# Structural boundary — the mapper only knows about engine exceptions
# ============================================================================


def test_mapper_only_accepts_engine_exception_types():
    """Type-guard: the mapper signature accepts only
    PrologEngineUnavailable. If someone extends it to accept a bare
    HTTPException or a raw status code, gateway-origin errors could be
    routed through the mapper — the boundary the two assertions above
    depend on.

    Uses `typing.get_type_hints` to resolve the annotation through
    `from __future__ import annotations` (which stringifies annotations at
    parse time). A change that widens the accepted type set will surface
    here as a test failure naming the exact class that changed.
    """
    import typing

    from api.lib import engine_error_mapper
    from api.prolog_client import PrologEngineUnavailable

    hints = typing.get_type_hints(engine_error_mapper.map_engine_error_to_http)
    exc_hint = hints.get("exc")
    assert exc_hint is PrologEngineUnavailable, (
        f"Mapper `exc` type hint resolves to {exc_hint!r}, not "
        f"PrologEngineUnavailable. If this widening is intentional, update "
        f"the boundary tests in this file + re-audit which gateway-origin "
        f"errors could now traverse the mapper's 4xx partition."
    )
