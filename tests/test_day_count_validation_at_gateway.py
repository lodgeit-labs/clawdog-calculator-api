"""Fable cell 13 mc22 2026-09-04: day_count validated at gateway.

Fable verbatim (Q1 ratification): *"a caller who can choose the
convention on /range/ but not on /at/ faces an asymmetry with no
justification, and unlike numeric_mode this is a legitimate caller
choice rather than an internal knob. Ratified."*

*"But it must be constrained at the gateway to the same literals as
/range/. If the gateway forwards an arbitrary string and the engine
rejects it, the caller gets a 502 engine_unavailable for what is
plainly a 422. That is the exact error-taxonomy defect that produced
the FBT class-6 finding. Add a thirteenth cell: /at/ with day_count:
'act/360' -> 422 at the gateway, engine never reached."*
"""
from __future__ import annotations

from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes.calculators import get_prolog_client

UNSCOPED_URI = "urn:sbrm:period:depreciation:unscoped"
UNSCOPED_ENCODED = quote(UNSCOPED_URI, safe="")


class _AssertNotCalledPrologClient:
    """Fake PrologClient that raises if the engine is dispatched to.

    Used to prove the engine is NOT reached on a Pydantic-rejected
    request (the whole point of cell 13).
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def depreciation_at(self, period_uri: str, payload: dict) -> dict:
        self.calls.append(f"depreciation_at({period_uri})")
        raise AssertionError(
            "Engine dispatch fired but should have been rejected at "
            "the gateway Pydantic layer. Fable cell 13 defect."
        )

    async def depreciation_range(self, period_uri: str, payload: dict) -> dict:
        self.calls.append(f"depreciation_range({period_uri})")
        raise AssertionError(
            "Engine dispatch fired but should have been rejected at "
            "the gateway Pydantic layer. Fable cell 13 defect."
        )


@pytest.fixture
def gateway_client() -> TestClient:
    fake = _AssertNotCalledPrologClient()

    async def _override():
        return fake

    app.dependency_overrides[get_prolog_client] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _at_body(day_count: str) -> dict:
    return {
        "basis": "accounting",
        "asset": {
            "cost": "10000.00",
            "acquisition_date": "2023-07-01",
            "accounting_useful_life_years": 5,
            "accounting_method": "prime_cost",
        },
        "at_date": "2023-07-31",
        "day_count": day_count,
    }


def _range_body(day_count: str) -> dict:
    return {
        "basis": "accounting",
        "asset": {
            "cost": "10000.00",
            "acquisition_date": "2023-07-01",
            "accounting_useful_life_years": 5,
            "accounting_method": "prime_cost",
        },
        "from_date": "2023-08-01",
        "to_date": "2023-08-31",
        "day_count": day_count,
    }


@pytest.mark.parametrize(
    "bogus_day_count",
    [
        "act/360",       # Fable's canonical bogus value
        "30/360",        # Bond-market convention (not depreciation)
        "actual/366",    # Off-by-one from the ratified constant-365
        "monthly-average",
        "",              # Empty string
        "ACTUAL/ACTUAL", # Case-sensitive check
    ],
)
def test_at_endpoint_rejects_bogus_day_count_at_gateway_pydantic(
    gateway_client: TestClient, bogus_day_count: str,
) -> None:
    """Fable cell 13 verbatim: /at/ with day_count 'act/360' -> 422 at
    the gateway, engine never reached.

    Extended to a spread of bogus values (parametrised) so a future
    silent-accept regression on any of them fails the run.
    """
    r = gateway_client.post(
        f"/v1/calculators/depreciation/at/{UNSCOPED_ENCODED}",
        json=_at_body(bogus_day_count),
    )
    assert r.status_code == 422, (
        f"day_count={bogus_day_count!r}: expected 422 at gateway; got "
        f"{r.status_code}: {r.text}"
    )
    detail = r.json().get("detail", [])
    # The Pydantic error should name day_count in the loc field.
    assert any(
        "day_count" in str(err.get("loc", "")) for err in detail
    ), f"Pydantic error should name day_count in loc: {detail!r}"


@pytest.mark.parametrize(
    "bogus_day_count",
    ["act/360", "30/360", "actual/366", "", "ACTUAL/ACTUAL"],
)
def test_range_endpoint_rejects_bogus_day_count_at_gateway_pydantic(
    gateway_client: TestClient, bogus_day_count: str,
) -> None:
    """Sibling of cell 13 for /range/. Same discipline."""
    r = gateway_client.post(
        f"/v1/calculators/depreciation/range/{UNSCOPED_ENCODED}",
        json=_range_body(bogus_day_count),
    )
    assert r.status_code == 422, (
        f"day_count={bogus_day_count!r}: expected 422 at gateway; got "
        f"{r.status_code}: {r.text}"
    )


@pytest.mark.parametrize(
    "good_day_count",
    ["actual/actual", "actual/365", "monthly"],
)
def test_at_endpoint_accepts_ratified_day_count_literals(
    good_day_count: str,
) -> None:
    """Sanity: the ratified literals are accepted at the gateway.

    This test does NOT dispatch to a fake engine; it just verifies the
    Pydantic model accepts the literal.
    """
    from api.schemas.depreciation import DepreciationAtInput
    m = DepreciationAtInput.model_validate({
        "basis": "accounting",
        "asset": {
            "cost": "10000.00",
            "acquisition_date": "2023-07-01",
            "accounting_useful_life_years": 5,
            "accounting_method": "prime_cost",
        },
        "at_date": "2023-07-31",
        "day_count": good_day_count,
    })
    assert m.day_count == good_day_count


def test_at_endpoint_accepts_omitted_day_count_at_pydantic_layer() -> None:
    """Cell-13 sibling: /at/ WITHOUT day_count MUST NOT be rejected by
    Pydantic at the gateway.

    The field is optional at /at/ (Fable D4 mc17 ruling: /at/ is live
    in the gateway registry; a required field breaks integrated
    callers). This test verifies the Pydantic model itself accepts a
    payload with day_count absent — that is the sole layer that could
    turn the F19-preserving optional into a breaking-required.
    """
    from api.schemas.depreciation import DepreciationAtInput

    m = DepreciationAtInput.model_validate({
        "basis": "accounting",
        "asset": {
            "cost": "10000.00",
            "acquisition_date": "2023-07-01",
            "accounting_useful_life_years": 5,
            "accounting_method": "prime_cost",
        },
        "at_date": "2023-07-31",
        # day_count deliberately omitted
    })
    assert m.day_count is None, (
        f"omitting day_count on /at/ MUST default to None (which the "
        f"gateway echoes as 'actual/actual' at response time per Fable "
        f"D4 mc17); got {m.day_count!r}"
    )
