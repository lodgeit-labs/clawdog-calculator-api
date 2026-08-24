"""Phase D Div7A gateway route smoke test (mut-2026-08-24-mc20).

Onboarding test for the Div7A_Engine gateway route. Hermetic; mirrors the
depreciation-audit smoke shape:

    Pydantic input validation
       → FastAPI in-process call
       → mocked Div7A_Engine backend (recorded response)
       → response shape passthrough
       → transport failure mapping (502/504)

Binary-failure assertions:
  1. Endpoint registered at the documented URL shape.
  2. Engine response forwarded byte-faithfully (no field renaming).
  3. Pydantic input validation rejects malformed payloads.
  4. Unsupported period_uri returns HTTP 404.
  5. Engine-unavailable maps to gateway HTTP 502 (not bare 500).

Full canonical algorithm verification lives in Div7A_Engine's own
`tests/differential/test_python_vs_prolog.py` (two-technique parity).
This gateway smoke only verifies the routing + forwarding + failure-mapping
surfaces.
"""
from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.prolog_client import PrologEngineUnavailable

PERIOD_URI = "urn:sbrm:period:div7a:fy2025"
PERIOD_URI_ENCODED = quote(PERIOD_URI, safe="")

CANONICAL_INPUT = {
    "amalgamated_base": 70000,
    "loan_term_years": 7,
    "loan_origination_date": "2024-06-01",
    "income_year_start_date": "2024-07-01",
    "is_first_real_myr_year": True,
    "repayments": [],
}

CANONICAL_ENGINE_RESPONSE = {
    "period_uri": PERIOD_URI,
    "amalgamated_base": "70000.0",
    "benchmark_rate": "0.0877",
    "remaining_term_years": 6,
    "statutory_myr": "15497.53",
    "total_repayments": "0.00",
    "shortfall": "15497.53",
    "is_complying": False,
    "deemed_dividend": "15497.53",
    "interest_accrued": "6122.18",
}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as tc:
        yield tc


def test_div7a_at_route_registered(client: TestClient) -> None:
    """The Div7A route accepts POSTs at the documented URL shape."""
    with patch(
        "api.routes.calculators.PrologClient.div7a_at",
        new_callable=AsyncMock,
        return_value=CANONICAL_ENGINE_RESPONSE,
    ):
        resp = client.post(
            f"/v1/calculators/div7a/at/{PERIOD_URI_ENCODED}",
            json=CANONICAL_INPUT,
        )
    assert resp.status_code == 200, resp.text


def test_div7a_at_forwards_engine_response(client: TestClient) -> None:
    """Engine response is passed through byte-faithfully."""
    with patch(
        "api.routes.calculators.PrologClient.div7a_at",
        new_callable=AsyncMock,
        return_value=CANONICAL_ENGINE_RESPONSE,
    ):
        resp = client.post(
            f"/v1/calculators/div7a/at/{PERIOD_URI_ENCODED}",
            json=CANONICAL_INPUT,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body == CANONICAL_ENGINE_RESPONSE, (
        f"gateway must not rewrite engine response; got diff. Body: {body}"
    )


def test_div7a_at_rejects_malformed_input(client: TestClient) -> None:
    """Pydantic validation rejects missing required fields."""
    resp = client.post(
        f"/v1/calculators/div7a/at/{PERIOD_URI_ENCODED}",
        json={"amalgamated_base": 70000},  # missing everything else
    )
    assert resp.status_code == 422, resp.text


def test_div7a_at_unsupported_period_returns_404(client: TestClient) -> None:
    """Unsupported period_uri (not in registry) returns HTTP 404."""
    unsupported = quote("urn:sbrm:period:div7a:fy2099", safe="")
    resp = client.post(
        f"/v1/calculators/div7a/at/{unsupported}",
        json=CANONICAL_INPUT,
    )
    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert "div7a" in body.get("detail", "").lower()


def test_div7a_at_engine_unavailable_maps_to_502(client: TestClient) -> None:
    """PrologEngineUnavailable (transport failure) maps to gateway HTTP 502."""
    engine_error = PrologEngineUnavailable(
        error_code="connect_error",
        detail="ECONNREFUSED",
        engine="div7a",
        url="http://localhost:8083",
    )
    with patch(
        "api.routes.calculators.PrologClient.div7a_at",
        new_callable=AsyncMock,
        side_effect=engine_error,
    ):
        resp = client.post(
            f"/v1/calculators/div7a/at/{PERIOD_URI_ENCODED}",
            json=CANONICAL_INPUT,
        )
    assert resp.status_code == 502, resp.text
    body = resp.json()
    assert body["detail"]["error"] == "div7a_engine_unavailable"
    assert body["detail"]["error_code"] == "connect_error"


def test_div7a_at_timeout_maps_to_504(client: TestClient) -> None:
    """PrologEngineUnavailable with 'timeout' error_code maps to HTTP 504."""
    engine_error = PrologEngineUnavailable(
        error_code="timeout",
        detail="read timeout after 30s",
        engine="div7a",
        url="http://localhost:8083",
    )
    with patch(
        "api.routes.calculators.PrologClient.div7a_at",
        new_callable=AsyncMock,
        side_effect=engine_error,
    ):
        resp = client.post(
            f"/v1/calculators/div7a/at/{PERIOD_URI_ENCODED}",
            json=CANONICAL_INPUT,
        )
    assert resp.status_code == 504, resp.text
