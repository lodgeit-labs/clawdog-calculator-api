"""Tax-depreciation gateway route smoke test.

Onboarding test for the tax-depreciation-engine gateway route (paired gateway
half of tax-depreciation-calculator#1). Hermetic; mirrors the div7a-at smoke
shape:

    Pydantic input (verbatim-forward)
       → FastAPI in-process call
       → mocked tax-depreciation-engine backend (recorded response)
       → response shape passthrough + manifest/advisory wrap
       → transport failure mapping (502/504)

Binary-failure assertions:
  1. Endpoint registered at the documented URL shape, for each of the three
     engine calculators (decline-in-value, low-value-pool, small-business-pool).
  2. Engine response forwarded byte-faithfully (no field renaming) + the
     gateway adds manifest + advisory blocks.
  3. The gateway templates the {calculator} path segment into the engine call.
  4. Unknown {calculator} segment returns HTTP 404.
  5. Unsupported period_uri returns HTTP 404.
  6. Engine-unavailable maps to gateway HTTP 502 (not bare 500); timeout → 504.
  7. The three calculators appear in GET /v1/calculators and GET /v1/modules
     under the tax-depreciation module.

**Two-depreciations discipline.** This is AU TAX depreciation (ITAA 1997
Division 40 / Subdivision 328-D), distinct from the accounting depreciation
(AASB 116) module. This gateway smoke only verifies routing + forwarding +
failure-mapping + discovery surfaces; the statutory algorithm lives in the
engine's own repo.
"""
from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.prolog_client import PrologEngineUnavailable

PERIOD_URI = "urn:sbrm:period:tax-depreciation:fy2025"
PERIOD_URI_ENCODED = quote(PERIOD_URI, safe="")

CALCULATORS = ("decline-in-value", "low-value-pool", "small-business-pool")

CANONICAL_INPUT = {
    "opening_balance": "10000.00",
    "additions": "0.00",
}

CANONICAL_ENGINE_RESPONSE = {
    "period_uri": PERIOD_URI,
    "deduction": "3000.00",
    "closing_balance": "7000.00",
    "trace": {"method": "diminishing_value", "rate": "0.30"},
    "rate_uris_consumed": [],
}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as tc:
        yield tc


@pytest.mark.parametrize("calculator", CALCULATORS)
def test_tax_depreciation_route_registered(
    client: TestClient, calculator: str
) -> None:
    """The route accepts POSTs at the documented URL shape for each calc."""
    with patch(
        "api.routes.calculators.PrologClient.tax_depreciation",
        new_callable=AsyncMock,
        return_value=CANONICAL_ENGINE_RESPONSE,
    ):
        resp = client.post(
            f"/v1/calculators/tax-depreciation/{calculator}/{PERIOD_URI_ENCODED}",
            json=CANONICAL_INPUT,
        )
    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize("calculator", CALCULATORS)
def test_tax_depreciation_forwards_engine_response_and_wraps(
    client: TestClient, calculator: str
) -> None:
    """Engine response fields pass through byte-faithfully; gateway adds the
    manifest + advisory envelope (mirrors the div7a wrap)."""
    with patch(
        "api.routes.calculators.PrologClient.tax_depreciation",
        new_callable=AsyncMock,
        return_value=CANONICAL_ENGINE_RESPONSE,
    ):
        resp = client.post(
            f"/v1/calculators/tax-depreciation/{calculator}/{PERIOD_URI_ENCODED}",
            json=CANONICAL_INPUT,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key, val in CANONICAL_ENGINE_RESPONSE.items():
        assert body.get(key) == val, (
            f"gateway must not rewrite engine field {key!r}; "
            f"expected {val!r} got {body.get(key)!r}"
        )
    # Manifest block added by the gateway wrap. rate_uris_consumed is empty,
    # so an honest empty rate_table_uris list is emitted (no fabricated anchor).
    assert "manifest" in body, "gateway must add manifest block"
    assert body["manifest"].get("rate_table_uris") == []
    # Advisory block added by wrap_response.
    assert "advisory" in body, "gateway must add advisory block"
    assert body["advisory"].get("jurisdiction") == "AU"


def test_tax_depreciation_templates_calculator_segment(client: TestClient) -> None:
    """The gateway passes the {calculator} path segment to the engine call
    verbatim (engine-id dispatch)."""
    captured: dict = {}

    async def _fake(self, calculator, period_uri, payload):
        captured["calculator"] = calculator
        captured["period_uri"] = period_uri
        captured["payload"] = payload
        return CANONICAL_ENGINE_RESPONSE

    with patch(
        "api.routes.calculators.PrologClient.tax_depreciation",
        new=_fake,
    ):
        resp = client.post(
            f"/v1/calculators/tax-depreciation/low-value-pool/{PERIOD_URI_ENCODED}",
            json=CANONICAL_INPUT,
        )
    assert resp.status_code == 200, resp.text
    assert captured["calculator"] == "low-value-pool"
    assert captured["period_uri"] == PERIOD_URI
    assert captured["payload"]["opening_balance"] == "10000.00"


def test_tax_depreciation_unknown_calculator_returns_404(client: TestClient) -> None:
    """An unsupported {calculator} segment returns HTTP 404 naming the set."""
    resp = client.post(
        f"/v1/calculators/tax-depreciation/not-a-calculator/{PERIOD_URI_ENCODED}",
        json=CANONICAL_INPUT,
    )
    assert resp.status_code == 404, resp.text
    detail = resp.json().get("detail", "")
    assert "decline-in-value" in detail


def test_tax_depreciation_unsupported_period_returns_404(client: TestClient) -> None:
    """Unsupported period_uri (not fy2025/fy2026) returns HTTP 404."""
    unsupported = quote("urn:sbrm:period:tax-depreciation:fy2099", safe="")
    resp = client.post(
        f"/v1/calculators/tax-depreciation/decline-in-value/{unsupported}",
        json=CANONICAL_INPUT,
    )
    assert resp.status_code == 404, resp.text
    assert "tax-depreciation" in resp.json().get("detail", "")


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
            json=CANONICAL_INPUT,
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
            json=CANONICAL_INPUT,
        )
    assert resp.status_code == 504, resp.text


def test_tax_depreciation_generic_route_dispatches(client: TestClient) -> None:
    """The generic POST /v1/calculators/{calc_uri}/{period_uri} route delegates
    to the native tax-depreciation handler (internal dispatch), returning the
    wrapped engine response rather than a 500."""
    calc_uri = quote("urn:sbrm:calculator:tax-depreciation:small-business-pool", safe="")
    with patch(
        "api.routes.calculators.PrologClient.tax_depreciation",
        new_callable=AsyncMock,
        return_value=CANONICAL_ENGINE_RESPONSE,
    ):
        resp = client.post(
            f"/v1/calculators/{calc_uri}/{PERIOD_URI_ENCODED}",
            json=CANONICAL_INPUT,
        )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("deduction") == "3000.00"


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
    # supported_periods carries both income years.
    for c in calcs:
        assert set(c["supported_periods"]) == {
            "urn:sbrm:period:tax-depreciation:fy2025",
            "urn:sbrm:period:tax-depreciation:fy2026",
        }

    mods = client.get("/v1/modules").json()
    module_uris = {m["module_uri"] for m in mods}
    assert "urn:sbrm:module:tax-depreciation" in module_uris
