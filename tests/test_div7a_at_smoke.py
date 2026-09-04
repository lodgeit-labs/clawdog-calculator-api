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
    """Engine response fields are passed through byte-faithfully.

    Post-mc35-2026-08-28: the gateway now wraps the engine response with a
    manifest (rate_table_uris + content_hash) and advisory block matching the
    FBT+depreciation self-declaration shape. The engine's own fields must
    still appear byte-faithfully in the response; the added envelope is
    additive, not a rewrite.
    """
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
    # Engine's own fields survive verbatim.
    for key, val in CANONICAL_ENGINE_RESPONSE.items():
        assert body.get(key) == val, (
            f"gateway must not rewrite engine field {key!r}; "
            f"expected {val!r} got {body.get(key)!r}"
        )
    # Manifest block is added by the gateway wrap.
    assert "manifest" in body, "gateway must add manifest block (mc35)"
    manifest_uris = body["manifest"].get("rate_table_uris", [])
    assert len(manifest_uris) >= 1, (
        "manifest must cite ≥ 1 rate URI (benchmark-interest fallback)"
    )
    for entry in manifest_uris:
        assert entry.get("content_hash"), "each rate URI must carry content_hash"
        assert entry.get("hash_algorithm") == "sha256"
    # Advisory block added by wrap_response.
    assert "advisory" in body, "gateway must add advisory block (mc35)"
    assert body["advisory"].get("jurisdiction") == "AU"


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
    """PrologEngineUnavailable with 'engine_timeout' error_code maps to HTTP 504.

    mc00-2026-09-04 (Fable D8a mapper refactor + Fable Flag-1/Amendment 2
    timeout correction):

    The historic Div7A handler checked `exc.error_code == "timeout"` and
    emitted 504. That code path was dead — PrologClient.dispatch()
    actually emits `error_code="engine_timeout"` (canonical slug). Evidence:

        $ grep -n 'error_code=' api/prolog_client.py
        289:                error_code="engine_unreachable",
        296:                error_code="engine_timeout",
        303:                error_code="engine_http_error",
        315:                error_code="engine_transport_error",

        $ grep -rn 'error_code="timeout"' api/
        (no matches)

    So the old 504 mapping never fired in production; it only fired for
    this test. The test was the only caller of the dead code path (Fable
    in-flight-note flag 2: "a mapping whose only caller was a test is the
    same artefact class as a validator with no consumer"). The old
    handler's `if exc.error_code == "timeout"` branch has been *removed*
    alongside this test rewrite — the central mapper only knows the
    canonical `engine_timeout` slug.

    Fable Flag-1 / Amendment 2 correction (mc00 05:09 UTC): engine_timeout
    maps to 504 Gateway Timeout, NOT 503. The request was sent, the engine
    did not respond in time — textbook 504. Div7A's ORIGINAL 504 assertion
    was right; FBT and depreciation historic 503 are corrected UP to 504
    via the central mapper, achieving symmetry in the right direction.

    Retitled `_to_504` (the digit that was correct at the start).
    """
    engine_error = PrologEngineUnavailable(
        error_code="engine_timeout",
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
