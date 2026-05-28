"""Route-level tests asserting structured 5xx surfacing on PrologEngineUnavailable.

Introduced under mc06-2026-05-28 Option-C PR α (Andrew direct-voice ratified
2026-05-28 10:34 UTC).

Closes OT #83 #1 (depreciation route returns bare HTML 500 on production
because DEPRECIATION_PROLOG_URL is unset and httpx.ConnectError is uncaught);
defends FBT route in depth against the symmetric failure mode.

Both calling routes (FBT car operating-cost + depreciation audit) MUST return
a structured JSON 5xx body when the upstream Prolog engine is unreachable,
NEVER a bare HTML 500. This is the Standing Rule #12 clause (e) assertion
applied at the FastAPI bridge layer.

Hermetic; uses httpx.MockTransport to simulate the four failure modes that
mc06's PrologClient.dispatch() now catches:
  - ConnectError (engine_unreachable)
  - TimeoutException (engine_timeout)
  - HTTPStatusError 4xx/5xx (engine_http_error)
  - RemoteProtocolError + other HTTPError (engine_transport_error)

Lessons honoured:
  #40 — production-bundle hermetic mock + symmetric live-prod parity
         (mc03 + mc06 pre-flight wire-confirmed depreciation route returns
         500 today; this test asserts the new shape after Option-C PR α lands).
  #36 — the catch lives in the PrologClient (bridge layer), not duplicated
         across two route handlers; both routes get structured surfacing
         for free.
  #37 — production surface, not wind-tunnel: the assertions check the live
         FastAPI route response body content-type + JSON structure, not the
         PrologClient internals (those are covered by test_prolog_client_dispatch.py).
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RATE_TABLE_FIXTURE = FIXTURES_DIR / "sbrm_rate_table_fy2026"
DEPRECIATION_FIXTURE_ROOT = FIXTURES_DIR / "sbrm_rate_table_depreciation_fy2026"

FBT_CALC_URI = "urn:sbrm:calculator:fbt:car-operating-cost"
FBT_PERIOD_URI = "urn:sbrm:period:fbt:fy2026"
DEP_PERIOD_URI = "urn:sbrm:period:depreciation:fy2026"

FBT_VALID_PAYLOAD = {
    "businessUsePercentage": 75,
    "formOfFinance": "owned",
    "fuelRepairsServicing": 3000,
    "registrationInsurance": 1500,
    "employeeContribution": 200,
    "noPrivateUseReduction": 0,
    "acquisitionCost": 50000,
    "acquisitionDate": "2024-01-01",
}

DEP_VALID_PAYLOAD = {
    "transitionDate": "2025-07-01",
    "method": "primecost",
    "assetsToAudit": [
        {
            "assetId": "test-1",
            "assetName": "Toyota Corolla",
            "purchaseDate": "2020-07-01",
            "originalCost": 30000,
            "taxMethod": "pc",
            "currentBookAccumDep": 15000,
        }
    ],
}


def _build_test_client(
    mock_transport: httpx.MockTransport,
    monkeypatch: pytest.MonkeyPatch,
    *,
    use_depreciation_rate_root: bool = False,
) -> TestClient:
    """Wire a TestClient with the mocked transport overriding the PrologClient dep."""
    from api.main import app
    from api.prolog_client import PrologClient
    from api.routes.calculators import get_prolog_client

    # If the test fires depreciation, the rate-table root needs to be the
    # depreciation fixture so the manifest builder doesn't 502 BEFORE the
    # PrologClient is even called (the manifest is built post-engine in the
    # depreciation handler; FBT path uses the FBT root).
    if use_depreciation_rate_root and DEPRECIATION_FIXTURE_ROOT.is_dir():
        monkeypatch.setenv(
            "CLAWDOG_RATE_TABLE_ROOT", str(DEPRECIATION_FIXTURE_ROOT)
        )

    mocked_client = httpx.AsyncClient(transport=mock_transport)

    async def _override() -> PrologClient:
        return PrologClient(
            base_url="http://fbt-engine.test",
            depreciation_base_url="http://dep-engine.test",
            client=mocked_client,
        )

    app.dependency_overrides[get_prolog_client] = _override
    client = TestClient(app)
    # Ensure cleanup happens; pytest manages dependency_overrides via the
    # caller's monkeypatch finalization where possible.
    return client


def _connect_error_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def _timeout_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectTimeout("connect timeout", request=request)


def _http_503_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, text="Service Unavailable")


def _remote_protocol_error_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.RemoteProtocolError("malformed", request=request)


# ============================================================================
# FBT route — structured 5xx on engine unreachable (defence in depth)
# ============================================================================


def test_fbt_route_returns_structured_502_on_connect_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """FBT route returns structured JSON 502 (not bare HTML 500) when engine
    is unreachable. This is the SR #12 clause (e) defence-in-depth assertion;
    today the FBT engine IS reachable so this never fires in prod, but the
    catch must work to keep parity with the depreciation route's live failure
    mode."""
    transport = httpx.MockTransport(_connect_error_handler)
    client = _build_test_client(transport, monkeypatch)
    try:
        url = f"/v1/calculators/{quote(FBT_CALC_URI, safe='')}/{quote(FBT_PERIOD_URI, safe='')}"
        resp = client.post(url, json=FBT_VALID_PAYLOAD)
    finally:
        from api.main import app
        from api.routes.calculators import get_prolog_client
        app.dependency_overrides.pop(get_prolog_client, None)

    assert resp.status_code == 502, f"expected 502 not {resp.status_code}; body={resp.text[:200]}"
    assert resp.headers["content-type"].startswith("application/json"), \
        f"expected JSON content-type, got {resp.headers.get('content-type')!r}"
    body = resp.json()
    detail = body.get("detail", {})
    assert detail.get("error") == "engine_unavailable"
    assert detail.get("error_code") == "engine_unreachable"
    assert detail.get("engine") == "fbt"


def test_fbt_route_returns_503_on_timeout(monkeypatch: pytest.MonkeyPatch):
    """FBT route returns 503 (not 502) when engine times out."""
    transport = httpx.MockTransport(_timeout_handler)
    client = _build_test_client(transport, monkeypatch)
    try:
        url = f"/v1/calculators/{quote(FBT_CALC_URI, safe='')}/{quote(FBT_PERIOD_URI, safe='')}"
        resp = client.post(url, json=FBT_VALID_PAYLOAD)
    finally:
        from api.main import app
        from api.routes.calculators import get_prolog_client
        app.dependency_overrides.pop(get_prolog_client, None)

    assert resp.status_code == 503
    body = resp.json()
    detail = body.get("detail", {})
    assert detail.get("error_code") == "engine_timeout"


def test_fbt_route_returns_502_on_engine_5xx(monkeypatch: pytest.MonkeyPatch):
    """FBT route returns 502 when engine returns its own 5xx (HTTPStatusError)."""
    transport = httpx.MockTransport(_http_503_handler)
    client = _build_test_client(transport, monkeypatch)
    try:
        url = f"/v1/calculators/{quote(FBT_CALC_URI, safe='')}/{quote(FBT_PERIOD_URI, safe='')}"
        resp = client.post(url, json=FBT_VALID_PAYLOAD)
    finally:
        from api.main import app
        from api.routes.calculators import get_prolog_client
        app.dependency_overrides.pop(get_prolog_client, None)

    assert resp.status_code == 502
    body = resp.json()
    detail = body.get("detail", {})
    assert detail.get("error_code") == "engine_http_error"
    assert detail.get("detail", {}).get("status_code") == 503


# ============================================================================
# Depreciation route — structured 5xx on engine unreachable (the LIVE failure)
# ============================================================================


def test_depreciation_route_returns_structured_502_on_connect_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """LOAD-BEARING: depreciation route returns structured JSON 502 (not bare
    HTML 500) when engine is unreachable. This is THE OT #83 #1 closure
    assertion. Wire-verified at mc03 06:05 UTC + mc06 pre-flight 10:30 UTC
    that the route currently 500s with content-type text/plain; after this
    PR lands, the same input must return JSON 502."""
    transport = httpx.MockTransport(_connect_error_handler)
    client = _build_test_client(
        transport, monkeypatch, use_depreciation_rate_root=True
    )
    try:
        url = f"/v1/calculators/depreciation/audit/{quote(DEP_PERIOD_URI, safe='')}"
        resp = client.post(url, json=DEP_VALID_PAYLOAD)
    finally:
        from api.main import app
        from api.routes.calculators import get_prolog_client
        app.dependency_overrides.pop(get_prolog_client, None)

    assert resp.status_code == 502, \
        f"expected 502 (OT #83 #1 closure), got {resp.status_code}; body={resp.text[:200]}"
    assert resp.headers["content-type"].startswith("application/json"), \
        f"expected JSON content-type (NOT bare-HTML 500), got {resp.headers.get('content-type')!r}"
    body = resp.json()
    detail = body.get("detail", {})
    assert detail.get("error") == "engine_unavailable"
    assert detail.get("error_code") == "engine_unreachable"
    assert detail.get("engine") == "depreciation"


def test_depreciation_route_returns_503_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
):
    """Depreciation route returns 503 when engine times out."""
    transport = httpx.MockTransport(_timeout_handler)
    client = _build_test_client(
        transport, monkeypatch, use_depreciation_rate_root=True
    )
    try:
        url = f"/v1/calculators/depreciation/audit/{quote(DEP_PERIOD_URI, safe='')}"
        resp = client.post(url, json=DEP_VALID_PAYLOAD)
    finally:
        from api.main import app
        from api.routes.calculators import get_prolog_client
        app.dependency_overrides.pop(get_prolog_client, None)

    assert resp.status_code == 503
    body = resp.json()
    detail = body.get("detail", {})
    assert detail.get("error_code") == "engine_timeout"


def test_depreciation_route_returns_502_on_transport_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """Depreciation route returns 502 on httpx.RemoteProtocolError + other
    transport-layer failures."""
    transport = httpx.MockTransport(_remote_protocol_error_handler)
    client = _build_test_client(
        transport, monkeypatch, use_depreciation_rate_root=True
    )
    try:
        url = f"/v1/calculators/depreciation/audit/{quote(DEP_PERIOD_URI, safe='')}"
        resp = client.post(url, json=DEP_VALID_PAYLOAD)
    finally:
        from api.main import app
        from api.routes.calculators import get_prolog_client
        app.dependency_overrides.pop(get_prolog_client, None)

    assert resp.status_code == 502
    body = resp.json()
    detail = body.get("detail", {})
    assert detail.get("error_code") == "engine_transport_error"


# ============================================================================
# Parametric symmetry — same failure shape across both routes
# ============================================================================


@pytest.mark.parametrize(
    "route_fixture",
    [
        pytest.param(
            (
                f"/v1/calculators/{quote(FBT_CALC_URI, safe='')}/{quote(FBT_PERIOD_URI, safe='')}",
                FBT_VALID_PAYLOAD,
                "fbt",
                False,
            ),
            id="fbt",
        ),
        pytest.param(
            (
                f"/v1/calculators/depreciation/audit/{quote(DEP_PERIOD_URI, safe='')}",
                DEP_VALID_PAYLOAD,
                "depreciation",
                True,
            ),
            id="depreciation",
        ),
    ],
)
def test_both_routes_emit_structured_json_on_engine_unreachable(
    route_fixture, monkeypatch: pytest.MonkeyPatch
):
    """Parametric assertion: BOTH FBT and depreciation routes emit structured
    JSON 502 with the same response shape on engine_unreachable. Closes the
    bare-HTML-500 surface across both routes symmetrically (per mc06 ratified
    Correction 2: defence-in-depth)."""
    url, payload, expected_engine, use_dep_root = route_fixture
    transport = httpx.MockTransport(_connect_error_handler)
    client = _build_test_client(
        transport, monkeypatch, use_depreciation_rate_root=use_dep_root
    )
    try:
        resp = client.post(url, json=payload)
    finally:
        from api.main import app
        from api.routes.calculators import get_prolog_client
        app.dependency_overrides.pop(get_prolog_client, None)

    assert resp.status_code == 502
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    detail = body.get("detail", {})
    assert detail.get("error") == "engine_unavailable"
    assert detail.get("error_code") == "engine_unreachable"
    assert detail.get("engine") == expected_engine
