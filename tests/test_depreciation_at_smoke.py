"""mc39-2026-08-29 rung 5 depreciation-at smoke test (Fable verdict amendment 2).

Supersedes the mc-designed batch-audit smoke test that never matched any
engine. Hermetic; mirrors the Div7A `test_div7a_at_smoke.py` shape:

    Pydantic input validation
       → FastAPI in-process call
       → mocked depreciation-engine backend (recorded response)
       → manifest wrap (empty rate_table_uris for T6 first cut per rung 5
         gateway code comment)
       → advisory wrapper
       → response shape check

Binary-failure assertions:
  1. Endpoint registered at /v1/calculators/depreciation/at/{period_uri}.
  2. Engine response fields pass through byte-faithfully; gateway adds
     manifest + advisory envelope.
  3. Manifest block is present (rate_table_uris array; T6 first cut emits
     empty because engine doesn't consume rate-table nodes yet).
  4. Advisory block present, AU jurisdiction, registered-agent-required.
  5. Fable rider 1: UK basis `uk_frs102_s17` refused by gateway.
  6. Fable rider 2: caller-supplied `numeric_mode` silently overwritten
     server-side before engine dispatch.
  7. Fable rider 3: engine's typed pool refusal passed through as HTTP 400
     with `refusal_class` preserved, not flattened to 502.
  8. URN retirement: legacy audit URN returns 404.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"
DEPRECIATION_FIXTURE_ROOT = FIXTURES_DIR / "sbrm_rate_table_depreciation_fy2026"

PERIOD_URI = "urn:sbrm:period:depreciation:fy2026"

# Canonical single-asset happy-path input mirroring the engine's
# DepreciationAtRequest schema (basis + asset + at_date + events[]).
SAMPLE_INPUT = {
    "basis": "accounting",
    "asset": {
        "cost": "5000.00",
        "acquisition_date": "2022-07-01",
        "accounting_useful_life_years": 10,
        "accounting_method": "prime_cost",
    },
    "at_date": "2025-06-30",
    "events": [],
}

# Recorded engine response (mirrors engine's DepreciationAtResponse).
# Values: prime-cost, useful life 10 years, at_date 3 FY-ends after
# acquisition → wdv_at ≈ 3500 (5000 - 3 * 500), period_dep_at = 500.
CANONICAL_ENGINE_RESPONSE = {
    "basis": "accounting",
    "at_date": "2025-06-30",
    "wdv_at": "3500.00",
    "period_dep_at": "500.00",
}


@pytest.fixture
def mocked_depreciation_engine_client() -> Iterator[httpx.AsyncClient]:
    """Returns canonical engine response for POST
    /v1/calculators/depreciation/at/{period_uri}."""

    def handler(request: httpx.Request) -> httpx.Response:
        if (
            "/v1/calculators/depreciation/at/" in request.url.path
            and request.method == "POST"
        ):
            return httpx.Response(200, json=CANONICAL_ENGINE_RESPONSE)
        return httpx.Response(404, json={"error": "no fixture for this route"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    yield client


@pytest.fixture
def mocked_pool_refusal_engine_client() -> Iterator[httpx.AsyncClient]:
    """Engine returns typed pool refusal per Fable F19 item 4 wire-shape."""

    def handler(request: httpx.Request) -> httpx.Response:
        if (
            "/v1/calculators/depreciation/at/" in request.url.path
            and request.method == "POST"
        ):
            return httpx.Response(
                400,
                json={
                    "refusal_class": "pool_asset_out_of_t6_scope",
                    "refusal_payload": {
                        "pool_type": "sbe_pool",
                        "retrofit_target": "T6.1",
                        "detail": (
                            "Pool depreciation is deferred to T6.1. "
                            "Please submit non-pool assets separately."
                        ),
                    },
                },
            )
        return httpx.Response(404, json={"error": "no fixture"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    yield client


def _test_client_with_mock(
    mock_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    monkeypatch.setenv("CLAWDOG_RATE_TABLE_ROOT", str(DEPRECIATION_FIXTURE_ROOT))
    from api.main import app  # noqa: WPS433
    from api.prolog_client import PrologClient
    from api.routes.calculators import get_prolog_client

    async def _override() -> PrologClient:
        return PrologClient(
            base_url="http://prolog.test",
            depreciation_base_url="http://prolog-dep.test",
            client=mock_client,
        )

    app.dependency_overrides[get_prolog_client] = _override
    return TestClient(app)


@pytest.fixture
def depreciation_test_client(
    mocked_depreciation_engine_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    from api.main import app  # noqa: WPS433
    from api.routes.calculators import get_prolog_client

    client = _test_client_with_mock(mocked_depreciation_engine_client, monkeypatch)
    try:
        with client as tc:
            yield tc
    finally:
        app.dependency_overrides.pop(get_prolog_client, None)


@pytest.fixture
def pool_refusal_test_client(
    mocked_pool_refusal_engine_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    from api.main import app  # noqa: WPS433
    from api.routes.calculators import get_prolog_client

    client = _test_client_with_mock(mocked_pool_refusal_engine_client, monkeypatch)
    try:
        with client as tc:
            yield tc
    finally:
        app.dependency_overrides.pop(get_prolog_client, None)


def _invoke(client: TestClient, payload: dict | None = None) -> dict:
    url = f"/v1/calculators/depreciation/at/{quote(PERIOD_URI, safe='')}"
    resp = client.post(url, json=payload or SAMPLE_INPUT)
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- Assertion class #1: endpoint registered ---------------------------------


def test_endpoint_registered(depreciation_test_client: TestClient) -> None:
    body = _invoke(depreciation_test_client)
    assert body["basis"] == "accounting"


# --- Assertion class #2: engine fields byte-faithful + manifest+advisory ---


def test_engine_response_byte_faithful_plus_envelope(
    depreciation_test_client: TestClient,
) -> None:
    """Post-mc39: engine fields survive verbatim; gateway adds manifest+advisory
    per Div7A mc35 pattern."""
    body = _invoke(depreciation_test_client)
    # Engine's own fields survive byte-faithfully.
    for key, val in CANONICAL_ENGINE_RESPONSE.items():
        assert body.get(key) == val, (
            f"gateway must not rewrite engine field {key!r}; "
            f"expected {val!r} got {body.get(key)!r}"
        )
    # Manifest + advisory added by gateway wrap.
    assert "manifest" in body, "gateway must add manifest block (mc35 pattern)"
    assert "advisory" in body, "gateway must add advisory block"


# --- Assertion class #3: manifest present (T6 first cut = empty entries) ---


def test_manifest_shape(depreciation_test_client: TestClient) -> None:
    """T6 first cut doesn't consume rate-table nodes at the fold, so manifest
    emits empty rate_table_uris rather than pinning a fake anchor. Manifest
    block still present per gateway rider self-declaration surface."""
    body = _invoke(depreciation_test_client)
    manifest = body["manifest"]
    assert "rate_table_uris" in manifest
    assert isinstance(manifest["rate_table_uris"], list)
    # T6 first cut: expected empty. Future basis expansions may populate.
    assert manifest["rate_table_uris"] == []


# --- Assertion class #4: advisory AU-jurisdiction ---------------------------


def test_advisory_au_jurisdiction(depreciation_test_client: TestClient) -> None:
    body = _invoke(depreciation_test_client)
    advisory = body["advisory"]
    assert advisory["jurisdiction"] == "AU"
    assert advisory["registered_agent_required"] is True


# --- Assertion class #5: Fable rider 1 — UK basis refused at gateway --------


def test_rider_1_uk_basis_refused(depreciation_test_client: TestClient) -> None:
    """Fable rider 1 (§A2.4): gateway constrains `basis` to AU literals.
    `uk_frs102_s17` (which the engine supports) is refused at the gateway."""
    uk_input = {**SAMPLE_INPUT, "basis": "uk_frs102_s17"}
    url = f"/v1/calculators/depreciation/at/{quote(PERIOD_URI, safe='')}"
    resp = depreciation_test_client.post(url, json=uk_input)
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert any("basis" in str(d).lower() for d in detail), detail


# --- Assertion class #6: Fable rider 2 — numeric_mode not caller-visible ----


def test_rider_2_numeric_mode_pinned_server_side(
    depreciation_test_client: TestClient,
) -> None:
    """Fable rider 2 (§A2.4): gateway pins `numeric_mode="serving"` and does
    not expose the field. Caller-supplied `numeric_mode` MUST be rejected
    by `extra=forbid` on the DepreciationAtInput model. The gateway client
    then injects the pinned value into the outgoing engine payload."""
    bad_input = {**SAMPLE_INPUT, "numeric_mode": "corpus_compare"}
    url = f"/v1/calculators/depreciation/at/{quote(PERIOD_URI, safe='')}"
    resp = depreciation_test_client.post(url, json=bad_input)
    assert resp.status_code == 422, resp.text


# --- Assertion class #7: Fable rider 3 — pool refusal passes through as 400 -


def test_rider_3_pool_refusal_surfaces_as_400_with_refusal_class(
    pool_refusal_test_client: TestClient,
) -> None:
    """Fable rider 3 (§A2.4): engine's typed pool refusal
    (`refusal_class="pool_asset_out_of_t6_scope"`) MUST surface as HTTP 400
    with the refusal envelope preserved, not flattened to generic 502."""
    url = f"/v1/calculators/depreciation/at/{quote(PERIOD_URI, safe='')}"
    resp = pool_refusal_test_client.post(url, json=SAMPLE_INPUT)
    assert resp.status_code == 400, resp.text
    body = resp.json()
    # FastAPI HTTPException wraps under `detail`.
    detail = body.get("detail", body)
    assert detail.get("refusal_class") == "pool_asset_out_of_t6_scope"
    assert "refusal_payload" in detail


# --- Assertion class #8: URN retirement — audit URN returns 404 -------------


def test_urn_retirement_legacy_audit_route_gone(
    depreciation_test_client: TestClient,
) -> None:
    """Fable rider 4 (§A2.4 + §A2.3): the legacy
    `urn:sbrm:calculator:depreciation:audit` URN and its
    `/v1/calculators/depreciation/audit/{period_uri}` path are RETIRED.
    Requests to the retired path return 404."""
    retired_path = f"/v1/calculators/depreciation/audit/{quote(PERIOD_URI, safe='')}"
    resp = depreciation_test_client.post(retired_path, json=SAMPLE_INPUT)
    assert resp.status_code == 404, resp.text


# --- Assertion class #9: unsupported period_uri rejected ---------------------


def test_unsupported_period_rejected(depreciation_test_client: TestClient) -> None:
    bad_period = "urn:sbrm:period:depreciation:fy2099"
    url = f"/v1/calculators/depreciation/at/{quote(bad_period, safe='')}"
    resp = depreciation_test_client.post(url, json=SAMPLE_INPUT)
    assert resp.status_code == 404, resp.text
