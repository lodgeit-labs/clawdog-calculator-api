"""Phase 3c.3.B depreciation audit smoke test.

Onboarding test for the Depreciation Audit endpoint (Andrew + Tracer
ratified 2026-05-12 05:54 UTC). Hermetic; mirrors the FBT
`test_phase3a_e2e.py` shape:

    Pydantic input validation
       → FastAPI in-process call
       → mocked Depreciation Prolog backend (recorded response)
       → manifest-fidelity helper (vendored depreciation rate-tables)
       → advisory wrapper
       → response shape check

Binary-failure assertions:
  1. Endpoint registered at the documented URL shape.
  2. Engine response forwarded byte-faithfully (no field renaming).
  3. Manifest carries the audit-variance-threshold rate entry with a
     valid 64-hex content_hash.
  4. Advisory block present and AU-jurisdiction-flagged.
  5. Pydantic input validation rejects unsupported method values
     (Andrew's scope: prime cost + diminishing value only).

This test does NOT use ``CLAWDOG_RATE_TABLE_ROOT`` override at the
fbt fixture path; instead it injects its own depreciation fixture root
via a fixture-local monkeypatch so the FBT-side hermetic test stays
isolated.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"
DEPRECIATION_FIXTURE_ROOT = FIXTURES_DIR / "sbrm_rate_table_depreciation_fy2026"

PERIOD_URI = "urn:sbrm:period:depreciation:fy2026"

SAMPLE_INPUT = {
    "transitionDate": "2025-07-01",
    "method": "primecost",
    "assetsToAudit": [
        {
            "assetId": "10",
            "assetName": "Toyota",
            "purchaseDate": "2015-01-30",
            "originalCost": 26255,
            "taxMethod": "dv",
            "currentBookAccumDep": 24934.04,
        },
        {
            "assetId": "11",
            "assetName": "Corolla",
            "purchaseDate": "2010-10-01",
            "originalCost": 20000,
            "taxMethod": "pc",
            "currentBookAccumDep": 19766.72,
        },
    ],
}


@pytest.fixture
def depreciation_recorded_response() -> dict:
    """Recorded Prolog `/api/v1/depreciation/audit` response for the
    smoke-test input above. Two assets, both motor_vehicles, prime-cost
    ideal projection, no material variance."""
    with (FIXTURES_DIR / "prolog_response_depreciation_audit_smoke.json").open() as fh:
        return json.load(fh)


@pytest.fixture
def mocked_depreciation_prolog_client(
    depreciation_recorded_response: dict,
) -> Iterator[httpx.AsyncClient]:
    """``httpx.AsyncClient`` returning the recorded depreciation response
    for ``POST /api/v1/depreciation/audit``."""

    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.url.path == "/api/v1/depreciation/audit"
            and request.method == "POST"
        ):
            return httpx.Response(200, json=depreciation_recorded_response)
        return httpx.Response(404, json={"error": "no fixture for this route"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    yield client


@pytest.fixture
def depreciation_test_client(
    mocked_depreciation_prolog_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    """``TestClient`` with the depreciation fixture rate-table root and a
    mocked depreciation Prolog backend."""
    # Point the resolver at the depreciation leaf fixture (the conftest
    # autouse fixture sets CLAWDOG_RATE_TABLE_ROOT to the FBT path; we
    # override it here for these tests).
    monkeypatch.setenv("CLAWDOG_RATE_TABLE_ROOT", str(DEPRECIATION_FIXTURE_ROOT))

    from api.main import app  # noqa: WPS433
    from api.prolog_client import PrologClient
    from api.routes.calculators import get_prolog_client

    async def _override() -> PrologClient:
        return PrologClient(
            base_url="http://prolog.test",
            depreciation_base_url="http://prolog-dep.test",
            client=mocked_depreciation_prolog_client,
        )

    app.dependency_overrides[get_prolog_client] = _override
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_prolog_client, None)


def _invoke(client: TestClient) -> dict:
    url = f"/v1/calculators/depreciation/audit/{quote(PERIOD_URI, safe='')}"
    resp = client.post(url, json=SAMPLE_INPUT)
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- Assertion class #1: endpoint registered ---------------------------------


def test_endpoint_registered(depreciation_test_client: TestClient) -> None:
    """The /v1/calculators/depreciation/audit/{period_uri} route exists and
    returns 200 for a valid request."""
    body = _invoke(depreciation_test_client)
    assert body["status"] == "success"


# --- Assertion class #2: engine response byte-faithful -----------------------


def test_engine_response_byte_faithful(
    depreciation_test_client: TestClient,
) -> None:
    """Per CLAWDOG/110 §3.3 atom-vs-bridge: the bridge must not reshape the
    engine's atom-bearing fields. transition_date, method, and the per-asset
    rows pass through unchanged."""
    body = _invoke(depreciation_test_client)
    assert body["transition_date"] == "2025-07-01"
    assert body["method"] == "primecost"
    assets = body["audited_standard_assets"]
    assert len(assets) == 2
    assert {a["asset_id"] for a in assets} == {"10", "11"}
    # Per-asset interpretation fields (method_flag, variance_flag) pass through
    # unchanged — the bridge does NOT re-interpret them.
    toyota = next(a for a in assets if a["asset_id"] == "10")
    assert "Warning" in toyota["method_flag"]
    corolla = next(a for a in assets if a["asset_id"] == "11")
    assert corolla["method_flag"] == "OK"


# --- Assertion class #3: manifest carries the rate URI -----------------------


def test_manifest_carries_audit_variance_threshold(
    depreciation_test_client: TestClient,
) -> None:
    """The depreciation manifest exposes the audit-variance-threshold rate
    URI with a valid 64-hex content_hash."""
    body = _invoke(depreciation_test_client)
    manifest = body["manifest"]
    entries = manifest["rate_table_uris"]
    assert isinstance(entries, list)
    assert len(entries) >= 1
    audit_var = next(
        (
            e
            for e in entries
            if "audit-variance-threshold" in e["uri"]
        ),
        None,
    )
    assert audit_var is not None, f"audit-variance-threshold missing from {entries}"
    assert audit_var["hash_algorithm"] == "sha256"
    assert len(audit_var["content_hash"]) == 64
    assert all(ch in "0123456789abcdef" for ch in audit_var["content_hash"])


# --- Assertion class #4: advisory block present + AU-flagged ----------------


def test_advisory_au_jurisdiction(
    depreciation_test_client: TestClient,
) -> None:
    """Depreciation audit responses carry an AU advisory block (registered
    agent required)."""
    body = _invoke(depreciation_test_client)
    advisory = body["advisory"]
    assert advisory["jurisdiction"] == "AU"
    assert advisory["registered_agent_required"] is True


# --- Assertion class #5: input validation forbids out-of-scope methods ------


def test_unsupported_method_rejected(
    depreciation_test_client: TestClient,
) -> None:
    """Andrew's accounting scope (2026-05-12 05:54 UTC): prime cost +
    diminishing value only. Any other method value must be rejected by the
    pydantic schema BEFORE the engine sees it.

    The IAWO / pool methods (pool-write-down, immediate-write-off, etc.)
    are tax-side concepts that don't belong in the accounting-side audit
    endpoint. The Literal["primecost", "dvmethod"] type forecloses smuggling.
    """
    bad_input = {**SAMPLE_INPUT, "method": "iawo"}
    url = f"/v1/calculators/depreciation/audit/{quote(PERIOD_URI, safe='')}"
    resp = depreciation_test_client.post(url, json=bad_input)
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert any("method" in str(d).lower() for d in detail), detail


# --- Assertion class #6: unsupported period_uri rejected ---------------------


def test_unsupported_period_rejected(
    depreciation_test_client: TestClient,
) -> None:
    """A period URI not in the registry's supported_periods list returns 404."""
    bad_period = "urn:sbrm:period:depreciation:fy2099"
    url = f"/v1/calculators/depreciation/audit/{quote(bad_period, safe='')}"
    resp = depreciation_test_client.post(url, json=SAMPLE_INPUT)
    assert resp.status_code == 404, resp.text


# --- Assertion class #7: empty assets batch rejected ------------------------


def test_empty_assets_batch_rejected(
    depreciation_test_client: TestClient,
) -> None:
    """The schema enforces min_length=1 on assetsToAudit; empty batches are
    semantic nonsense and the engine should never see them."""
    empty_input = {**SAMPLE_INPUT, "assetsToAudit": []}
    url = f"/v1/calculators/depreciation/audit/{quote(PERIOD_URI, safe='')}"
    resp = depreciation_test_client.post(url, json=empty_input)
    assert resp.status_code == 422, resp.text
