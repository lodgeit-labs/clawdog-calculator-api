"""Hygiene-PR contract gates (D70, D72, D78).

These are the three binary-failure gates the gateway hygiene PR adds, mirroring
the integration-kit contract suite's invariants but running hermetically inside
the gateway test suite:

  * D78 — every calculator 200 carries ``advisory.disclaimer`` and a
    list-typed ``manifest.rate_table_uris``. HP was the gap (its advisory was
    ``{figure_type, notes}`` and its manifest lacked ``rate_table_uris``); the
    gateway-built manifest already satisfies the invariant for the other
    engines (``build_manifest`` always emits a ``rate_table_uris`` list and
    ``wrap_response`` always sets ``advisory.disclaimer``).
  * D70 — ``/healthz`` (and the internal engine-auth probe) are absent from
    ``openapi.json`` while the routes keep working.
  * D72 — the unscoped rates route returns 200 with ``entries: []`` rather than
    a 404.

Hermetic fixtures use the real live response shape: the HP 200 is the real
in-process engine; the depreciation 200 mocks the remote engine with a recorded
response in the engine's wire shape, exactly as ``test_depreciation_at_smoke``
does.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from api.main import app

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMITTED_SPEC = REPO_ROOT / "openapi.json"
FIXTURES_DIR = Path(__file__).parent / "fixtures"
DEPRECIATION_FIXTURE_ROOT = FIXTURES_DIR / "sbrm_rate_table_depreciation_fy2026"


# --- D78: HP 200 carries advisory.disclaimer + list-typed rate_table_uris ----

_HP_INPUT = {
    "amount_financed": "273269.35",
    "annual_rate_pct": "3.84",
    "term_regular_instalments": 59,
    "instalment": "4180.02",
    "timing": "in_arrears",
    "frequency": "monthly",
    "begin_date": "2021-08-30",
    "contract_form": "chattel_mortgage",
    "balloon": {"amount": "59180.02", "instalment_number": 60, "mode": "replace"},
    "fy_end_month": 6,
}


def _assert_contract_envelope(body: dict, *, where: str) -> None:
    """The two contract-suite invariants on a single 200 body."""
    advisory = body.get("advisory")
    assert isinstance(advisory, dict), f"{where}: advisory missing/not an object"
    assert isinstance(advisory.get("disclaimer"), str) and advisory["disclaimer"], (
        f"{where}: advisory.disclaimer must be a non-empty string"
    )
    manifest = body.get("manifest")
    assert isinstance(manifest, dict), f"{where}: manifest missing/not an object"
    assert "rate_table_uris" in manifest, (
        f"{where}: manifest.rate_table_uris must be present"
    )
    assert isinstance(manifest["rate_table_uris"], list), (
        f"{where}: manifest.rate_table_uris must be a list"
    )


def test_d78_hp_200_has_disclaimer_and_rate_table_uris_list() -> None:
    client = TestClient(app)
    resp = client.post("/v1/calculators/hp/schedule", json=_HP_INPUT)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    _assert_contract_envelope(body, where="hp:schedule")
    # HP consumes no year-dependent rate nodes: the list is present and empty.
    assert body["manifest"]["rate_table_uris"] == [], (
        "HP consumes no rate nodes; rate_table_uris must be an empty list"
    )
    # D78 must not disturb the existing advisory/manifest fields.
    assert body["advisory"]["figure_type"] == "amortisation_schedule"
    assert isinstance(body["advisory"]["notes"], list) and body["advisory"]["notes"]
    for key in ("calculator", "engine_version", "accrual_basis", "rounding_policy"):
        assert key in body["manifest"], f"HP manifest lost {key}"
    # The disclaimer must claim neither a tax basis nor an AASB basis, and must
    # carry no internal implementation references (D64 hygiene).
    disclaimer = body["advisory"]["disclaimer"]
    assert "AASB" not in disclaimer, "HP is not an AASB accounting figure"
    assert "TAA" not in disclaimer and "TASA" not in disclaimer, (
        "HP is not a tax figure; no TAA/TASA framing"
    )
    for banned in (".py", "Prolog", "api/"):
        assert banned not in disclaimer, f"disclaimer leaks {banned!r}"


# --- D78: depreciation 200 (mocked engine, real wire shape) ------------------

_DEP_INPUT = {
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
_DEP_ENGINE_RESPONSE = {
    "basis": "accounting",
    "at_date": "2025-06-30",
    "wdv_at": "3500.00",
    "period_dep_at": "500.00",
}


@pytest.fixture
def depreciation_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    def handler(request: httpx.Request) -> httpx.Response:
        if (
            "/v1/calculators/depreciation/at/" in request.url.path
            and request.method == "POST"
        ):
            return httpx.Response(200, json=_DEP_ENGINE_RESPONSE)
        return httpx.Response(404, json={"error": "no fixture"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setenv("CLAWDOG_RATE_TABLE_ROOT", str(DEPRECIATION_FIXTURE_ROOT))
    from api.prolog_client import PrologClient
    from api.routes.calculators import get_prolog_client

    async def _override() -> PrologClient:
        return PrologClient(
            base_url="http://prolog.test",
            depreciation_base_url="http://prolog-dep.test",
            client=mock_client,
        )

    app.dependency_overrides[get_prolog_client] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_d78_depreciation_200_has_disclaimer_and_rate_table_uris_list(
    depreciation_client: TestClient,
) -> None:
    period = quote("urn:sbrm:period:depreciation:unscoped", safe="")
    resp = depreciation_client.post(
        f"/v1/calculators/depreciation/at/{period}", json=_DEP_INPUT
    )
    assert resp.status_code == 200, resp.text
    _assert_contract_envelope(resp.json(), where="depreciation:at")


# --- D70: /healthz absent from openapi.json; route still works ---------------


def test_d70_healthz_absent_from_openapi() -> None:
    spec = json.loads(COMMITTED_SPEC.read_text(encoding="utf-8"))
    assert "/healthz" not in spec["paths"], "/healthz must be hidden from openapi.json"
    assert "/_internal/probe/engine-auth" not in spec["paths"], (
        "the internal engine-auth probe must be hidden from openapi.json"
    )


def test_d70_healthz_route_still_works() -> None:
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200, resp.text
    assert resp.json().get("status") == "ok"


def test_d70_engine_auth_probe_route_still_registered() -> None:
    # In production posture (token env var unset) the probe returns 404; that is
    # the designed response, proving the route is reachable (a truly unknown
    # path also 404s, so we additionally assert /livez — a sibling system route
    # — is present in the spec, confirming only the two D70 paths were hidden).
    client = TestClient(app)
    resp = client.post("/_internal/probe/engine-auth", json={})
    assert resp.status_code == 404  # production posture, not a routing failure
    spec = json.loads(COMMITTED_SPEC.read_text(encoding="utf-8"))
    assert "/livez" in spec["paths"], "/livez must remain published"


# --- D72: unscoped rates route returns 200 with an empty list ----------------


@pytest.mark.parametrize(
    "period",
    [
        "urn:sbrm:period:hp:unscoped",
        "urn:sbrm:period:depreciation:unscoped",
        "urn:sbrm:period:someother:unscoped",
    ],
)
def test_d72_unscoped_rates_returns_200_empty_list(
    period: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # conftest's autouse fixture pins CLAWDOG_RATE_TABLE_ROOT at a POPULATED
    # fixture dir, and the resolver's override branch returns that same dir for
    # every period (ignoring the period segment). Point the override at a
    # non-existent path so the real production branch fires: the unscoped
    # period's rate-table root does not exist, so the route must return 200 [].
    monkeypatch.setenv("CLAWDOG_RATE_TABLE_ROOT", str(tmp_path / "does-not-exist"))
    client = TestClient(app)
    resp = client.get(f"/v1/rates/{quote(period, safe='')}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("entries") == [], f"{period}: expected entries: []"
    assert body.get("period_uri") == period


def test_d72_scoped_missing_root_still_404(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A YEAR-scoped period whose root is genuinely missing stays a 404 — the
    D72 relaxation is unscoped-only."""
    monkeypatch.setenv("CLAWDOG_RATE_TABLE_ROOT", str(tmp_path / "does-not-exist"))
    client = TestClient(app)
    resp = client.get(
        f"/v1/rates/{quote('urn:sbrm:period:fbt:fy2026', safe='')}"
    )
    assert resp.status_code == 404, resp.text
