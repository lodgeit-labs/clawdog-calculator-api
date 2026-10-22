"""Tax-depreciation gateway route smoke test (SCOPE_tax_depreciation_v1.md v1.4).

Paired gateway half of lodgeit-labs/tax-depreciation-calculator#1. Hermetic;
mirrors the div7a-at smoke shape:

    per-calculator Pydantic input (money as decimal strings, cent-checked)
       → FastAPI in-process call
       → mocked tax-depreciation-engine backend (REAL recorded response shape)
       → response passthrough + gateway manifest/advisory wrap
       → refusal (400) + transport-failure (502/504) mapping

**Fixture provenance.** The mocked engine responses below use the engine's
REAL response shape, taken from the engine repo's own tests
(lodgeit-labs/tax-depreciation-calculator `tests/test_org1598_return40360.py`
and `app/engine/*.py` return dicts): top-level calculator fields
(`decline_in_value`, `deduction`, `closing_adjustable_value`,
`balancing_adjustment`, `closing_pool_balance`, `pool_decline_in_value`),
`trace`, `rate_uris_consumed`, and the engine-appended
`rounding_policy: "lodgeit-tax-depreciation-rounding-1.0"`. The figures are
LodgeiT Tax Depreciation report rows from org 1598, Company Tax Return 2025
(return 40360): Drill Press disposal (decline 5,030.16, loss 1,470) and the
low-value pool (34 → decline 13 → closing 21).

**Two-depreciations discipline.** This is AU TAX depreciation (ITAA 1997
Division 40 / Subdivision 328-D), distinct from the accounting depreciation
(AASB 116) module. The gateway smoke verifies routing, gateway-side input
validation (money cent-check + required effective_life_years), forwarding,
refusal + failure mapping, the Div 40 / Subdiv 328-D advisory, and discovery;
the statutory algorithm lives in the engine's own repo.
"""
from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.prolog_client import PrologCalculationError, PrologEngineUnavailable

PERIOD_URI = "urn:sbrm:period:tax-depreciation:fy2025"
PERIOD_URI_ENCODED = quote(PERIOD_URI, safe="")

CALCULATORS = ("decline-in-value", "low-value-pool", "small-business-pool")

# --- Valid gateway inputs (money as decimal strings, per-calculator schema) ---

# Drill Press disposal — org 1598 / return 40360, Dep1.png row. The gateway
# requires effective_life_years (no asset_description fallback) and money as
# decimal strings.
DRILL_PRESS_INPUT = {
    "method": "diminishing_value",
    "cost": "55000.00",
    "start_held_date": "2023-05-01",
    "effective_life_years": 10,
    "opening_adjustable_value": "42500.19",
    "disposal": {"date": "2025-02-01", "termination_value": "36000.01"},
}

LOW_VALUE_POOL_INPUT = {
    "opening_pool_balance": "34.00",
}

SMALL_BUSINESS_POOL_INPUT = {
    "opening_pool_balance": "61684.00",
}

_INPUT_BY_CALCULATOR = {
    "decline-in-value": DRILL_PRESS_INPUT,
    "low-value-pool": LOW_VALUE_POOL_INPUT,
    "small-business-pool": SMALL_BUSINESS_POOL_INPUT,
}

# --- REAL engine response shapes (from the engine repo's return dicts) --------

# decline_in_value.calculate() return shape (app/engine/decline_in_value.py).
# Drill Press figures from tests/test_org1598_return40360.py.
DRILL_PRESS_ENGINE_RESPONSE = {
    "days_held": 216,
    "rate": "20.0000",
    "decline_in_value": "5030.16",
    "deduction": "5030.16",
    "closing_adjustable_value": "37470.03",
    "balancing_adjustment": "-1470.00",
    "trace": {
        "engine_version": "lodgeit-tax-depreciation-calculators/0.1.0",
        "statute": "ITAA 1997 s 40-70 (diminishing value)",
        "balancing_adjustment_unrounded": "-1470.02",
    },
    "rate_uris_consumed": [],
    "rounding_policy": "lodgeit-tax-depreciation-rounding-1.0",
}

# low_value_pool.calculate() return shape (app/engine/low_value_pool.py).
# Opening 34.00 × 37.5% = 12.75 → 13 (whole dollars); closing 34 − 13 = 21.
LOW_VALUE_POOL_ENGINE_RESPONSE = {
    "decline_in_value": "13.00",
    "closing_pool_balance": "21.00",
    "assessable_amount": "0.00",
    "trace": {
        "engine_version": "lodgeit-tax-depreciation-calculators/0.1.0",
        "statute": "ITAA 1997 s 40-440 (low-value pool)",
        "decline_unrounded": "12.75",
    },
    "rate_uris_consumed": [],
    "rounding_policy": "lodgeit-tax-depreciation-rounding-1.0",
}

# small_business_pool.calculate() return shape. Opening 61,684 × 30% =
# 18,505.20 → 18,505; closing 61,684 − 18,505 = 43,179.
SMALL_BUSINESS_POOL_ENGINE_RESPONSE = {
    "pool_decline_in_value": "18505.00",
    "closing_pool_balance": "43179.00",
    "trace": {
        "engine_version": "lodgeit-tax-depreciation-calculators/0.1.0",
        "statute": "ITAA 1997 Subdiv 328-D (small business pool)",
        "pool_decline_unrounded": "18505.20",
    },
    "rate_uris_consumed": [],
    "rounding_policy": "lodgeit-tax-depreciation-rounding-1.0",
}

_ENGINE_RESPONSE_BY_CALCULATOR = {
    "decline-in-value": DRILL_PRESS_ENGINE_RESPONSE,
    "low-value-pool": LOW_VALUE_POOL_ENGINE_RESPONSE,
    "small-business-pool": SMALL_BUSINESS_POOL_ENGINE_RESPONSE,
}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as tc:
        yield tc


# ---------------------------------------------------------------------------
# 1. Route registered for each calculator.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("calculator", CALCULATORS)
def test_tax_depreciation_route_registered(
    client: TestClient, calculator: str
) -> None:
    """The route accepts POSTs at the documented URL shape for each calc."""
    with patch(
        "api.routes.calculators.PrologClient.tax_depreciation",
        new_callable=AsyncMock,
        return_value=_ENGINE_RESPONSE_BY_CALCULATOR[calculator],
    ):
        resp = client.post(
            f"/v1/calculators/tax-depreciation/{calculator}/{PERIOD_URI_ENCODED}",
            json=_INPUT_BY_CALCULATOR[calculator],
        )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 2a. Dep1 row — Drill Press decline + balancing adjustment forwarded exactly.
# ---------------------------------------------------------------------------
def test_drill_press_decline_and_balancing_forwarded(client: TestClient) -> None:
    """Dep1 (org 1598 / return 40360): the Drill Press disposal row. The engine
    figures (decline 5030.16, loss 1470 → balancing -1470.00) pass through the
    gateway byte-faithfully, and the gateway adds manifest + advisory."""
    with patch(
        "api.routes.calculators.PrologClient.tax_depreciation",
        new_callable=AsyncMock,
        return_value=DRILL_PRESS_ENGINE_RESPONSE,
    ):
        resp = client.post(
            f"/v1/calculators/tax-depreciation/decline-in-value/{PERIOD_URI_ENCODED}",
            json=DRILL_PRESS_INPUT,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decline_in_value"] == "5030.16"
    assert body["deduction"] == "5030.16"
    assert body["balancing_adjustment"] == "-1470.00"
    assert body["closing_adjustable_value"] == "37470.03"
    # §4.4: the unrounded figure sits beside the whole-dollar step in trace.
    assert body["trace"]["balancing_adjustment_unrounded"] == "-1470.02"
    # rounding_policy is the tax-depreciation policy, passed through from engine.
    assert body["rounding_policy"] == "lodgeit-tax-depreciation-rounding-1.0"
    # Gateway-added envelope.
    assert body["manifest"]["rate_table_uris"] == []
    assert body["advisory"]["jurisdiction"] == "AU"


# ---------------------------------------------------------------------------
# 2b. Low-value pool — 13 / 21 forwarded exactly.
# ---------------------------------------------------------------------------
def test_low_value_pool_13_21_forwarded(client: TestClient) -> None:
    """Dep2 (org 1598 / return 40360): the low-value pool. Opening 34 → decline
    13 → closing 21 (the report's own worked example of the whole-dollar rule),
    passed through the gateway byte-faithfully."""
    with patch(
        "api.routes.calculators.PrologClient.tax_depreciation",
        new_callable=AsyncMock,
        return_value=LOW_VALUE_POOL_ENGINE_RESPONSE,
    ):
        resp = client.post(
            f"/v1/calculators/tax-depreciation/low-value-pool/{PERIOD_URI_ENCODED}",
            json=LOW_VALUE_POOL_INPUT,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decline_in_value"] == "13.00"
    assert body["closing_pool_balance"] == "21.00"
    assert body["trace"]["decline_unrounded"] == "12.75"
    assert body["rounding_policy"] == "lodgeit-tax-depreciation-rounding-1.0"


# ---------------------------------------------------------------------------
# 2c. Advisory says Div 40 / Subdiv 328-D, not AASB 116 (§5).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("calculator", CALCULATORS)
def test_advisory_says_div40_328d_not_aasb116(
    client: TestClient, calculator: str
) -> None:
    """The advisory affirms the figure is a Division 40 / Subdivision 328-D tax
    figure and negates AASB 116, per SCOPE §5 — distinct from the accounting
    depreciation module's AASB 116 advisory."""
    with patch(
        "api.routes.calculators.PrologClient.tax_depreciation",
        new_callable=AsyncMock,
        return_value=_ENGINE_RESPONSE_BY_CALCULATOR[calculator],
    ):
        resp = client.post(
            f"/v1/calculators/tax-depreciation/{calculator}/{PERIOD_URI_ENCODED}",
            json=_INPUT_BY_CALCULATOR[calculator],
        )
    assert resp.status_code == 200, resp.text
    advisory = resp.json()["advisory"]
    disclaimer = advisory["disclaimer"]
    assert "Division 40" in disclaimer
    assert "Subdivision 328-D" in disclaimer
    assert "AASB 116" in disclaimer
    assert "not an accounting carrying amount" in disclaimer
    bases = {(s["statute"], s["section"]) for s in advisory["statutory_basis"]}
    assert ("ITAA 1997", "Division 40") in bases
    assert ("ITAA 1997", "Subdivision 328-D") in bases


# ---------------------------------------------------------------------------
# 2d. Engine {calculator} path segment templated verbatim.
# ---------------------------------------------------------------------------
def test_tax_depreciation_templates_calculator_segment(client: TestClient) -> None:
    """The gateway passes the {calculator} path segment to the engine call
    verbatim (engine-id dispatch), and forwards money as decimal strings."""
    captured: dict = {}

    async def _fake(self, calculator, period_uri, payload):
        captured["calculator"] = calculator
        captured["period_uri"] = period_uri
        captured["payload"] = payload
        return LOW_VALUE_POOL_ENGINE_RESPONSE

    with patch("api.routes.calculators.PrologClient.tax_depreciation", new=_fake):
        resp = client.post(
            f"/v1/calculators/tax-depreciation/low-value-pool/{PERIOD_URI_ENCODED}",
            json=LOW_VALUE_POOL_INPUT,
        )
    assert resp.status_code == 200, resp.text
    assert captured["calculator"] == "low-value-pool"
    assert captured["period_uri"] == PERIOD_URI
    # Money leaves the gateway as a decimal string (§10, the hp pattern).
    assert captured["payload"]["opening_pool_balance"] == "34.00"
    assert isinstance(captured["payload"]["opening_pool_balance"], str)


# ---------------------------------------------------------------------------
# 3. Refusal — engine {refusal_class, refusal_payload} → 400 engine:"tax-depreciation".
# ---------------------------------------------------------------------------
def test_tax_depreciation_refusal_maps_to_400_with_engine_name(
    client: TestClient,
) -> None:
    """A well-formed request the engine refuses (400 with {refusal_class,
    refusal_payload}) maps to a gateway 400 carrying engine: "tax-depreciation"
    via D63's _engine_name_for. Fixture: disposal_outside_income_year, one of
    the engine's starting refusal classes (§10)."""
    engine_error = PrologCalculationError(
        error="disposal_outside_income_year",
        detail={
            "refusal_class": "disposal_outside_income_year",
            "refusal_payload": {
                "message": (
                    "The disposal date 2025-11-15 is outside the income year "
                    "fy2025 (1 Jul 2024 – 30 Jun 2025)."
                ),
            },
        },
    )
    with patch(
        "api.routes.calculators.PrologClient.tax_depreciation",
        new_callable=AsyncMock,
        side_effect=engine_error,
    ):
        resp = client.post(
            f"/v1/calculators/tax-depreciation/decline-in-value/{PERIOD_URI_ENCODED}",
            json={
                **DRILL_PRESS_INPUT,
                "disposal": {"date": "2025-11-15", "termination_value": "1000.00"},
            },
        )
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    # Mapper envelope (engine_error_mapper): 400 + engine named via D63.
    assert detail["engine"] == "tax-depreciation"
    assert detail["engine_detail"]["refusal_class"] == "disposal_outside_income_year"


# ---------------------------------------------------------------------------
# 4. Missing effective_life_years → 422 naming the field (§2, §4).
# ---------------------------------------------------------------------------
def test_missing_effective_life_years_returns_422_naming_field(
    client: TestClient,
) -> None:
    """effective_life_years is required on decline-in-value with NO
    asset_description fallback (§2, §4). The gateway rejects a body without it
    with a 422 that names the field, before the engine is called."""
    body = {k: v for k, v in DRILL_PRESS_INPUT.items()}
    body.pop("effective_life_years")
    # asset_description is NOT a gateway field; supplying it must not rescue the
    # request (no fallback at the gateway).
    body["asset_description"] = "Drill Press"

    # The engine must never be reached — assert it is not called.
    mock = AsyncMock()
    with patch("api.routes.calculators.PrologClient.tax_depreciation", new=mock):
        resp = client.post(
            f"/v1/calculators/tax-depreciation/decline-in-value/{PERIOD_URI_ENCODED}",
            json=body,
        )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    # The 422 names effective_life_years in a loc path.
    locs = {str(loc) for err in detail for loc in err.get("loc", [])}
    assert "effective_life_years" in locs, detail
    mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# 4b. Sub-cent money → 422 money_not_cent_quantised (gateway cent-check, §5/§10).
# ---------------------------------------------------------------------------
def test_sub_cent_money_returns_422_cent_quantised(client: TestClient) -> None:
    """Money is cent-checked by the gateway (§5, §10): a sub-cent cost is
    rejected with a 422 before the engine is called."""
    body = {**DRILL_PRESS_INPUT, "cost": "55000.123"}
    mock = AsyncMock()
    with patch("api.routes.calculators.PrologClient.tax_depreciation", new=mock):
        resp = client.post(
            f"/v1/calculators/tax-depreciation/decline-in-value/{PERIOD_URI_ENCODED}",
            json=body,
        )
    assert resp.status_code == 422, resp.text
    mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# 5. Unknown calculator / unsupported period → 404.
# ---------------------------------------------------------------------------
def test_tax_depreciation_unknown_calculator_returns_404(client: TestClient) -> None:
    """An unsupported {calculator} segment returns HTTP 404 naming the set."""
    resp = client.post(
        f"/v1/calculators/tax-depreciation/not-a-calculator/{PERIOD_URI_ENCODED}",
        json=LOW_VALUE_POOL_INPUT,
    )
    assert resp.status_code == 404, resp.text
    assert "decline-in-value" in resp.json().get("detail", "")


def test_tax_depreciation_unsupported_period_returns_404(client: TestClient) -> None:
    """Unsupported period_uri (not fy2025/fy2026) returns HTTP 404."""
    unsupported = quote("urn:sbrm:period:tax-depreciation:fy2099", safe="")
    resp = client.post(
        f"/v1/calculators/tax-depreciation/low-value-pool/{unsupported}",
        json=LOW_VALUE_POOL_INPUT,
    )
    assert resp.status_code == 404, resp.text
    assert "tax-depreciation" in resp.json().get("detail", "")


# ---------------------------------------------------------------------------
# 6. Transport failure → 502; timeout → 504.
# ---------------------------------------------------------------------------
def test_tax_depreciation_engine_unavailable_maps_to_502(client: TestClient) -> None:
    """PrologEngineUnavailable (transport failure) maps to gateway HTTP 502."""
    engine_error = PrologEngineUnavailable(
        error_code="engine_unreachable",
        detail="ECONNREFUSED",
        engine="tax-depreciation",
        url="http://localhost:8084",
    )
    with patch(
        "api.routes.calculators.PrologClient.tax_depreciation",
        new_callable=AsyncMock,
        side_effect=engine_error,
    ):
        resp = client.post(
            f"/v1/calculators/tax-depreciation/decline-in-value/{PERIOD_URI_ENCODED}",
            json=DRILL_PRESS_INPUT,
        )
    assert resp.status_code == 502, resp.text
    body = resp.json()
    assert body["detail"]["error"] == "tax_depreciation_engine_unavailable"
    assert body["detail"]["error_code"] == "engine_unreachable"


def test_tax_depreciation_timeout_maps_to_504(client: TestClient) -> None:
    """PrologEngineUnavailable with 'engine_timeout' maps to HTTP 504."""
    engine_error = PrologEngineUnavailable(
        error_code="engine_timeout",
        detail="read timeout after 30s",
        engine="tax-depreciation",
        url="http://localhost:8084",
    )
    with patch(
        "api.routes.calculators.PrologClient.tax_depreciation",
        new_callable=AsyncMock,
        side_effect=engine_error,
    ):
        resp = client.post(
            f"/v1/calculators/tax-depreciation/decline-in-value/{PERIOD_URI_ENCODED}",
            json=DRILL_PRESS_INPUT,
        )
    assert resp.status_code == 504, resp.text


# ---------------------------------------------------------------------------
# 7. Generic route dispatches to the native handler (internal dispatch).
# ---------------------------------------------------------------------------
def test_tax_depreciation_generic_route_dispatches(client: TestClient) -> None:
    """The generic POST /v1/calculators/{calc_uri}/{period_uri} route delegates
    to the native tax-depreciation handler (internal dispatch), returning the
    wrapped engine response rather than a 500."""
    calc_uri = quote(
        "urn:sbrm:calculator:tax-depreciation:small-business-pool", safe=""
    )
    with patch(
        "api.routes.calculators.PrologClient.tax_depreciation",
        new_callable=AsyncMock,
        return_value=SMALL_BUSINESS_POOL_ENGINE_RESPONSE,
    ):
        resp = client.post(
            f"/v1/calculators/{calc_uri}/{PERIOD_URI_ENCODED}",
            json=SMALL_BUSINESS_POOL_INPUT,
        )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("pool_decline_in_value") == "18505.00"


# ---------------------------------------------------------------------------
# 8. Discovery — three calculators under the tax-depreciation module.
# ---------------------------------------------------------------------------
def test_tax_depreciation_discovery_listing(client: TestClient) -> None:
    """The three calculators appear in GET /v1/calculators under the
    tax-depreciation module, and the module appears in GET /v1/modules."""
    resp = client.get(
        "/v1/calculators", params={"module": "urn:sbrm:module:tax-depreciation"}
    )
    assert resp.status_code == 200, resp.text
    calcs = resp.json()
    uris = {c["calc_uri"] for c in calcs}
    assert uris == {
        "urn:sbrm:calculator:tax-depreciation:decline-in-value",
        "urn:sbrm:calculator:tax-depreciation:low-value-pool",
        "urn:sbrm:calculator:tax-depreciation:small-business-pool",
    }
    assert all(c["module"] == "urn:sbrm:module:tax-depreciation" for c in calcs)
    assert all(c["jurisdiction"] == "AU" for c in calcs)
    for c in calcs:
        assert set(c["supported_periods"]) == {
            "urn:sbrm:period:tax-depreciation:fy2025",
            "urn:sbrm:period:tax-depreciation:fy2026",
        }

    mods = client.get("/v1/modules").json()
    module_uris = {m["module_uri"] for m in mods}
    assert "urn:sbrm:module:tax-depreciation" in module_uris
