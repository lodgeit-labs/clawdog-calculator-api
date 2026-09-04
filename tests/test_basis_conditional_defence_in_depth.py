"""D8a defence-in-depth: gateway-side basis-conditional field validation.

**Fable post-matrix directive mc00-2026-09-04:** the central engine-error
mapper handles engine 4xx correctly (D8a: engine 422 → gateway 422 with
sanitised detail). But an engine round-trip for a caller's obvious mistake
is 100-300 ms the caller waits before seeing an actionable message; on
Cloud Run cold-start it is worse. The defence-in-depth layer catches KNOWN
engine basis-conditional rules at the pydantic layer, before dispatch.

Rule set (as of engine mc-2026-09-03 wire probe + D8c mc00-2026-09-04
narrowing, mirrored in
`api/schemas/depreciation.py::_validate_basis_conditional_asset_fields`):

  basis="accounting" REQUIRES asset.accounting_useful_life_years
                     REQUIRES asset.accounting_method
                     REFUSES  asset.tax_asset_class

  basis="tax"        REMOVED at pydantic type layer under D8c mc00-
                     2026-09-04. GatewayBasisLiteral =
                     Literal["accounting"] refuses `"tax"` at the
                     literal_error tier before this validator runs.
                     Tax basis re-widens via a separate URN + registry
                     entry when someone wants it.

Interaction with the mapper's Amendment-3 drift-detector:

  * Gateway pydantic catches KNOWN engine rules → gateway 422, no engine
    round-trip, no drift log. Fast path.
  * Engine grows a NEW rule the gateway hasn't learned → engine 422 →
    mapper's engine_validation_error → `gateway_engine_schema_drift`
    warning log line fires. This test file exercises both surfaces.

Fable ruling (verbatim):

    "Gateway-side conditional validation lands alongside [the mapper] as
     defence in depth so the engine is not reached for a caller error —
     but the mapper is the safety net and it ships first, because the
     next conditional rule the engine grows would otherwise reintroduce
     this."
"""
from __future__ import annotations

from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.main import app

DEP_AT_PERIOD = "urn:sbrm:period:depreciation:unscoped"
DEP_RANGE_PERIOD = "urn:sbrm:period:depreciation:unscoped"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _at_url() -> str:
    return f"/v1/calculators/depreciation/at/{quote(DEP_AT_PERIOD, safe='')}"


def _range_url() -> str:
    return f"/v1/calculators/depreciation/range/{quote(DEP_RANGE_PERIOD, safe='')}"


# ============================================================================
# accounting basis — missing required fields
# ============================================================================


def test_at_accounting_missing_useful_life_returns_gateway_422(
    client: TestClient,
) -> None:
    """The tester's most likely first mistake: `basis="accounting"` without
    `asset.accounting_useful_life_years`. Prior state (pre-D8a defence-in-
    depth): engine 422 → mapper `engine_validation_error`. New state:
    gateway 422 with the missing field named, no engine round-trip."""
    resp = client.post(
        _at_url(),
        json={
            "basis": "accounting",
            "asset": {
                "cost": "5000.00",
                "acquisition_date": "2022-07-01",
                # accounting_useful_life_years OMITTED (defect)
                "accounting_method": "prime_cost",
            },
            "at_date": "2025-06-30",
        },
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json().get("detail", "")
    detail_text = str(detail)
    assert "accounting_useful_life_years" in detail_text, (
        f"Gateway 422 must name the missing field. Got: {detail_text!r}"
    )
    # The mapper's drift-detector log must NOT fire — this defect was
    # caught by the gateway, not by the engine round-trip.
    # (Log absence is not asserted here; the mapper unit tests cover it.)


def test_at_accounting_missing_method_returns_gateway_422(
    client: TestClient,
) -> None:
    """basis=accounting missing accounting_method."""
    resp = client.post(
        _at_url(),
        json={
            "basis": "accounting",
            "asset": {
                "cost": "5000.00",
                "acquisition_date": "2022-07-01",
                "accounting_useful_life_years": 10,
                # accounting_method OMITTED (defect)
            },
            "at_date": "2025-06-30",
        },
    )
    assert resp.status_code == 422, resp.text
    assert "accounting_method" in str(resp.json().get("detail", ""))


def test_at_accounting_missing_both_names_both_in_one_error(
    client: TestClient,
) -> None:
    """When BOTH accounting fields are omitted, a single validation error
    should name both — the caller sees the whole gap, not just the first
    one that pydantic reached."""
    resp = client.post(
        _at_url(),
        json={
            "basis": "accounting",
            "asset": {
                "cost": "5000.00",
                "acquisition_date": "2022-07-01",
                # BOTH accounting fields OMITTED
            },
            "at_date": "2025-06-30",
        },
    )
    assert resp.status_code == 422, resp.text
    detail_text = str(resp.json().get("detail", ""))
    assert "accounting_useful_life_years" in detail_text
    assert "accounting_method" in detail_text


def test_range_accounting_missing_useful_life_returns_gateway_422(
    client: TestClient,
) -> None:
    """Same defence on /range/. Same defect class."""
    resp = client.post(
        _range_url(),
        json={
            "basis": "accounting",
            "asset": {
                "cost": "10000.00",
                "acquisition_date": "2023-07-01",
                # accounting_useful_life_years OMITTED (defect)
                "accounting_method": "prime_cost",
            },
            "from_date": "2023-08-01",
            "to_date": "2024-06-30",
            "day_count": "actual/actual",
        },
    )
    assert resp.status_code == 422, resp.text
    assert "accounting_useful_life_years" in str(
        resp.json().get("detail", "")
    )


# ============================================================================
# accounting basis — cross-field refusal (tax_asset_class present)
# ============================================================================


def test_at_accounting_with_tax_asset_class_is_refused(client: TestClient) -> None:
    """basis=accounting + tax_asset_class present is a mixed-basis payload;
    the engine's fold refuses it, so the gateway does too."""
    resp = client.post(
        _at_url(),
        json={
            "basis": "accounting",
            "asset": {
                "cost": "5000.00",
                "acquisition_date": "2022-07-01",
                "accounting_useful_life_years": 10,
                "accounting_method": "prime_cost",
                "tax_asset_class": "urn:sbrm:asset-class:office-equipment",
            },
            "at_date": "2025-06-30",
        },
    )
    assert resp.status_code == 422, resp.text
    detail_text = str(resp.json().get("detail", ""))
    assert "tax_asset_class" in detail_text
    assert "basis='accounting' refuses" in detail_text or "refuses" in detail_text


# ============================================================================
# tax basis — D8c mc00-2026-09-04 narrowed OUT: pydantic literal_error at
# the type layer BEFORE the defence-in-depth helper runs.
#
# Historic tests (pre-D8c) asserted tax-basis-missing-tax_asset_class
# behaviour that is now unreachable. Rewritten below to assert the NEW
# contract: any basis other than "accounting" fails at the gateway 422
# with pydantic's literal_error naming the accepted set.
#
# If GatewayBasisLiteral is ever re-widened without going through the
# "separate URN + separate registry entry + separate input schema" path
# Fable ruled at §5, these tests fire.
# ============================================================================


def test_at_tax_basis_is_narrowed_out_at_pydantic_layer(
    client: TestClient,
) -> None:
    """D8c: basis='tax' is refused at pydantic literal layer with a
    message naming 'accounting' as the only accepted value. Historic
    tax-basis-missing-tax_asset_class behaviour is unreachable through
    this URN; tax basis becomes a separate URN + registry entry when
    someone wants it."""
    resp = client.post(
        _at_url(),
        json={
            "basis": "tax",
            "asset": {
                "cost": "5000.00",
                "acquisition_date": "2022-07-01",
                "tax_asset_class": "urn:sbrm:asset-class:office-equipment",
            },
            "at_date": "2025-06-30",
        },
    )
    assert resp.status_code == 422, resp.text
    detail_text = str(resp.json().get("detail", ""))
    # pydantic emits literal_error with the accepted set explicit
    assert "accounting" in detail_text, (
        f"Refusal message must name 'accounting' as the accepted "
        f"basis. Got: {detail_text!r}"
    )
    assert "basis" in detail_text, (
        f"Refusal detail must locate the failure at 'basis'. Got: "
        f"{detail_text!r}"
    )


def test_range_tax_basis_is_narrowed_out_at_pydantic_layer(
    client: TestClient,
) -> None:
    """D8c parallel on /range/. Both routes share the same narrowed
    GatewayBasisLiteral; both refuse basis='tax' with the same message
    shape. Fable §5 concern (`/range/` accepting tax while claiming to
    be narrowed) is closed at both endpoints."""
    resp = client.post(
        _range_url(),
        json={
            "basis": "tax",
            "asset": {
                "cost": "10000.00",
                "acquisition_date": "2023-07-01",
                "tax_asset_class": "urn:sbrm:asset-class:office-equipment",
            },
            "from_date": "2023-08-01",
            "to_date": "2024-06-30",
            "day_count": "actual/actual",
        },
    )
    assert resp.status_code == 422, resp.text
    detail_text = str(resp.json().get("detail", ""))
    assert "accounting" in detail_text
    assert "basis" in detail_text


# ============================================================================
# happy paths — well-formed payloads must NOT be caught by defence-in-depth
# ============================================================================


def test_at_accounting_wellformed_reaches_engine(client: TestClient) -> None:
    """The defence-in-depth layer must be TRANSPARENT to well-formed
    payloads. If it 422s a valid payload, we've regressed. This test
    asserts the payload gets past the gateway pydantic layer — the response
    may still be a 5xx because there's no live engine under the TestClient,
    but the failure class must be transport (engine_unavailable /
    engine_unreachable), NOT validation."""
    resp = client.post(
        _at_url(),
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
    # If the payload got past pydantic, the failure surface will be a 5xx
    # transport error (no engine in TestClient) or a 200 (if engine is
    # accidentally reachable). What it must NOT be is 422.
    assert resp.status_code != 422, (
        f"Well-formed accounting payload rejected at gateway 422; "
        f"defence-in-depth regressed. Body: {resp.text[:300]}"
    )


# Historic test `test_at_tax_wellformed_reaches_engine` REMOVED under D8c.
# The behaviour it asserted (well-formed tax payload reaches engine) is
# no longer true because tax basis is narrowed out at pydantic. Leaving
# the removal recorded in commentary rather than deleting silently so a
# future reader searching for the historic test name finds the D8c
# reference.


def test_range_accounting_wellformed_reaches_engine(client: TestClient) -> None:
    """Range endpoint happy path."""
    resp = client.post(
        _range_url(),
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
    assert resp.status_code != 422, (
        f"Well-formed range payload rejected at gateway 422. "
        f"Body: {resp.text[:300]}"
    )
