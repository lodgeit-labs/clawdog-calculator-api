"""Pytest fixtures.

Tests run **hermetically**: no docker-compose, no live SWI-Prolog, no live
Cloud Run. The Prolog backend is mocked via ``httpx.MockTransport`` so every
test is fast and reproducible.

The vendored rate-table snapshot at ``tests/fixtures/sbrm_rate_table_fy2026/``
is the byte-content reference for the manifest-fidelity gate.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RATE_TABLE_FIXTURE = FIXTURES_DIR / "sbrm_rate_table_fy2026"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def rate_table_fixture() -> Path:
    return RATE_TABLE_FIXTURE


@pytest.fixture(autouse=True)
def _clawdog_rate_table_root_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Force the bridge to read the vendored rate-table snapshot.

    Tests must be hermetic — they cannot reach into the Brain repository
    out-of-process.
    """
    monkeypatch.setenv("CLAWDOG_RATE_TABLE_ROOT", str(RATE_TABLE_FIXTURE))
    yield


@pytest.fixture
def pr_d_case_5_response() -> dict:
    """Recorded Prolog response for PR-D 5th case (Phase 2l-OC-integrate)."""
    with (FIXTURES_DIR / "prolog_response_pr_d_case_5.json").open() as fh:
        return json.load(fh)


@pytest.fixture
def mocked_prolog_client(pr_d_case_5_response: dict) -> Iterator[httpx.AsyncClient]:
    """Yield an ``httpx.AsyncClient`` that returns the recorded fixture for
    ``POST /calculate_fbt`` and a stub for ``GET /health``."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calculate_fbt" and request.method == "POST":
            return httpx.Response(200, json=pr_d_case_5_response)
        if request.url.path == "/health" and request.method == "GET":
            return httpx.Response(200, json={"status": "ok", "rate_table_facts": 99})
        return httpx.Response(404, json={"error": "no fixture for this route"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    yield client
    # AsyncClient.aclose is async; pytest-anyio will dispose at session end.


@pytest.fixture
def fastapi_test_client(mocked_prolog_client: httpx.AsyncClient) -> Iterator[TestClient]:
    """FastAPI ``TestClient`` with the Prolog client dependency overridden."""
    from api.main import app  # noqa: WPS433
    from api.prolog_client import PrologClient
    from api.routes.calculators import get_prolog_client

    async def _override() -> PrologClient:
        return PrologClient(
            base_url="http://prolog.test",
            client=mocked_prolog_client,
        )

    app.dependency_overrides[get_prolog_client] = _override
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_prolog_client, None)
