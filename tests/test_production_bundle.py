"""Production-bundle binary-failure gate.

Phase 3a deemed-dispatch 500 root-cause regression test, **parametrised over
the ratified taxonomy set** at Phase 3c.2.c (`mut-2026-05-12-mc16`).

The hermetic E2E suite (`test_phase3a_e2e.py`) sets `CLAWDOG_RATE_TABLE_ROOT`
to a vendored fixture, which short-circuits the production resolver path.
That hermetic green hid a load-bearing defect at Phase 3a: the production
Docker image did not bundle the SBRM rate-table tree, so the production
`_rate_table_root_for(period_uri)` resolved to a non-existent path. Any
request whose engine response carried a non-empty `rate_uris_consumed`
tripped an uncaught `FileNotFoundError` inside `build_manifest` and surfaced
as a bare 500 to the caller.

This gate exercises the **production resolver** against the **production
bundle** (`rate_tables/SBRM_RATE_TABLE/`) shipped inside the Docker image.
It DOES NOT use `CLAWDOG_RATE_TABLE_ROOT`. If this gate is green, the
production manifest path is exercisable.

Phase 3c.2.c additions:

- Resolver path now reads `<calc>/<taxonomy>/<period_id>/` per CLAWDOG/111 NN#2.
- Assertions parametrise over the ratified taxonomy set
  `[lodgeit_au_sbrm, hoffman_base]` (Phase 3c.2 state: `lodgeit_au_sbrm` is
  populated; `hoffman_base` exists as an empty-ready directory and populates
  at Phase 3c.3 Depreciation_Transforms onboarding).
- Assertion class #1 (bundle existence) runs for both taxonomies (both
  directories must exist; `hoffman_base` may be empty).
- Assertion class #2 (file presence) runs only against taxonomies whose
  bundle is populated (currently `lodgeit_au_sbrm` only).
- Assertion class #4 (end-to-end dispatch) runs against `lodgeit_au_sbrm`
  with the existing PR-D Case 5 input.

Per Lesson #25 (Cut-over diff), Lesson #37 (the runway IS the production
surface), and Lesson #40 (hermetic green without production-bundle green
is pre-broken), this gate is the structural-completeness check the prior
test suite was missing.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

# The repo-root bundle that the Dockerfile copies into /app/SBRM_RATE_TABLE/.
# Cloud Run sets LODGEIT_FBT_REPO=/app so the resolver reaches
# /app/SBRM_RATE_TABLE/<calc>/<period_id>/. Locally we point LODGEIT_FBT_REPO
# at the repo root which contains rate_tables/SBRM_RATE_TABLE/... — the
# resolver is calc/period-aware so we point it at rate_tables/ to mirror
# the in-image layout (rate_tables/ -> /app/).
REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_BUNDLE_ROOT = REPO_ROOT / "rate_tables"

CALC_URI = "urn:sbrm:calculator:fbt:car-operating-cost"
PERIOD_URI = "urn:sbrm:period:fbt:fy2026"

# Ratified taxonomy set per CLAWDOG/111 §2 (PR #164 mut-2026-05-11-mc14).
# Mirrors api.lib.rate_table_resolver.RATIFIED_TAXONOMIES; duplicated here
# as a literal so the test is self-contained.
RATIFIED_TAXONOMIES = ["lodgeit_au_sbrm", "hoffman_base"]

# Phase 3c.2 state: lodgeit_au_sbrm bundle is populated; hoffman_base is
# empty-ready (populates at Phase 3c.3). Assertion class #2 (file presence)
# runs only against POPULATED bundles.
POPULATED_TAXONOMIES = ["lodgeit_au_sbrm"]

# PR-D Case 5 input — same canonical case as `test_phase3a_e2e.py`. The
# engine response is mocked here too (we are not testing the engine), but
# the manifest path is exercised against the real bundled files.
PR_D_CASE_5_INPUT = {
    "businessUsePercentage": 75,
    "employeeContribution": 200,
    "formOfFinance": "owned",
    "leasePayments": 0,
    "fuelRepairsServicing": 3000,
    "registrationInsurance": 1500,
    "noPrivateUseReduction": 0,
    "acquisitionDate": "2024-04-01",
    "openingDepreciatedValue": 55000,
    "daysHeldInFBTYear": 365,
}


@pytest.mark.parametrize("taxonomy", RATIFIED_TAXONOMIES)
def test_production_bundle_directory_exists(taxonomy: str) -> None:
    """Assertion class #1: every taxonomy in the ratified set has a bundle
    directory under the production rate-table tree.

    Parametrised over CLAWDOG/111 §2's ratified taxonomy set. Empty-ready
    directories are acceptable (the `hoffman_base` bundle is empty at Phase
    3c.2 and populates at Phase 3c.3); the existence check passes regardless
    of populated content.
    """
    assert PRODUCTION_BUNDLE_ROOT.is_dir(), (
        f"production rate-table bundle missing at {PRODUCTION_BUNDLE_ROOT}; "
        f"the Dockerfile expects to COPY rate_tables/SBRM_RATE_TABLE into the image"
    )
    taxonomy_dir = PRODUCTION_BUNDLE_ROOT / "SBRM_RATE_TABLE" / "fbt" / taxonomy
    assert taxonomy_dir.is_dir(), (
        f"production taxonomy bundle directory missing at {taxonomy_dir}; "
        f"the manifest resolver expects "
        f"<bundle>/SBRM_RATE_TABLE/<calc>/<taxonomy>/<period_id>/ "
        f"per CLAWDOG/111 NN#2 (Phase 3c.2 mut-2026-05-12-mc16). Adding a new "
        f"taxonomy to RATIFIED_TAXONOMIES requires shipping the bundle (or an "
        f"empty-ready directory) in the same PR per CLAWDOG/111 NN#5."
    )


@pytest.mark.parametrize("taxonomy", POPULATED_TAXONOMIES)
def test_production_bundle_contains_dispatch_rate_tables(taxonomy: str) -> None:
    """Assertion class #2: populated taxonomies MUST carry the three
    rate-table fact-nodes consumed by the deemed-dispatch path.

    Parametrised over POPULATED_TAXONOMIES (Phase 3c.2: `lodgeit_au_sbrm`
    only). `hoffman_base` joins this list when its FBT bundle populates.
    """
    fy2026 = PRODUCTION_BUNDLE_ROOT / "SBRM_RATE_TABLE" / "fbt" / taxonomy / "fy2026"
    required = [
        "deemed-depreciation-rates.md",
        "benchmark-interest.md",
        "days-in-year.md",
    ]
    for name in required:
        path = fy2026 / name
        assert path.is_file(), f"production bundle missing {path}"
        # And the file must be hashable (non-empty, decodable utf-8).
        text = path.read_text(encoding="utf-8")
        assert "content_hash" in text, f"{path} has no content_hash frontmatter line"


@pytest.mark.parametrize("taxonomy", POPULATED_TAXONOMIES)
def test_production_resolver_resolves_against_bundle(
    monkeypatch: pytest.MonkeyPatch,
    taxonomy: str,
) -> None:
    """Assertion class #3: `_rate_table_root_for` resolves to a populated
    production bundle when LODGEIT_FBT_REPO is wired the way Cloud Run wires
    it (no CLAWDOG_RATE_TABLE_ROOT override) and the taxonomy parameter is
    set explicitly."""
    from api.routes.calculators import _rate_table_root_for

    monkeypatch.delenv("CLAWDOG_RATE_TABLE_ROOT", raising=False)
    monkeypatch.setenv("LODGEIT_FBT_REPO", str(PRODUCTION_BUNDLE_ROOT))

    root = _rate_table_root_for(PERIOD_URI, taxonomy)
    assert root.is_dir(), f"resolver produced non-existent path {root}"
    assert (root / "deemed-depreciation-rates.md").is_file()


def _mock_dispatch_engine_response() -> dict:
    """Minimal engine response shape that triggers the manifest path with
    the three deemed-dispatch rate URIs."""
    rate_uris = [
        "urn:sbrm:rate:fbt:fy2026:deemed-depreciation-rates",
        "urn:sbrm:rate:fbt:fy2026:benchmark-interest",
        "urn:sbrm:rate:fbt:fy2026:days-in-year",
    ]
    return {
        "taxable_value": 5547.75,
        "rate_uris_consumed": rate_uris,
        "trace": {
            "applied_rate_table_uris": rate_uris,
            "deemed_dispatch": "computed",
            "form_of_finance": "owned",
            "deemed_depreciation": 13750.0,
            "deemed_interest": 4741.0,
            "deemed_total": 18491.0,
            "business_use_pct": 75,
            "business_use_reduction": 13868.25,
            "employee_contribution": 200.0,
            "fuel_repairs_servicing": 3000.0,
            "lease_payments": 0.0,
            "no_private_use_reduction": 0.0,
            "registration_insurance": 1500.0,
            "total_after_npur": 24991.0,
            "tv_before_operating": 5547.75,
            "tv_final": 5547.75,
            "tv_net_pre_clamp": 5547.75,
        },
    }


def test_dispatch_path_against_production_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: a deemed-dispatch request against the production resolver
    + production bundle MUST return 200 with a 3-entry manifest. This is the
    gate that would have caught the Phase 3a deemed-dispatch 500.

    We override the autouse `_clawdog_rate_table_root_env` (which forces
    hermetic CLAWDOG_RATE_TABLE_ROOT) and instead wire the production env
    shape: LODGEIT_FBT_REPO pointing at the in-repo bundle parent. This is
    structurally identical to Cloud Run's `LODGEIT_FBT_REPO=/app` against
    `/app/SBRM_RATE_TABLE/...`.
    """
    monkeypatch.delenv("CLAWDOG_RATE_TABLE_ROOT", raising=False)
    monkeypatch.setenv("LODGEIT_FBT_REPO", str(PRODUCTION_BUNDLE_ROOT))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calculate_fbt" and request.method == "POST":
            return httpx.Response(200, json=_mock_dispatch_engine_response())
        if request.url.path == "/health" and request.method == "GET":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404, json={"error": "unmocked route"})

    transport = httpx.MockTransport(handler)
    mock_client = httpx.AsyncClient(transport=transport)

    from api.main import app
    from api.prolog_client import PrologClient
    from api.routes.calculators import get_prolog_client

    async def _override() -> PrologClient:
        return PrologClient(base_url="http://prolog.test", client=mock_client)

    app.dependency_overrides[get_prolog_client] = _override
    try:
        with TestClient(app) as client:
            # Explicit taxonomy parameter exercises the post-mc16 query-param
            # path. Phase 3c.2: lodgeit_au_sbrm is the only populated bundle.
            url = (
                f"/v1/calculators/{quote(CALC_URI, safe='')}/"
                f"{quote(PERIOD_URI, safe='')}?taxonomy=lodgeit_au_sbrm"
            )
            resp = client.post(url, json=PR_D_CASE_5_INPUT)
    finally:
        app.dependency_overrides.pop(get_prolog_client, None)

    assert resp.status_code == 200, (
        f"Phase 3a deemed-dispatch 500 regression: production-bundle path "
        f"failed with {resp.status_code}: {resp.text[:500]}"
    )
    body = resp.json()
    assert body["taxable_value"] == pytest.approx(5547.75, abs=0.01)

    entries = body["manifest"]["rate_table_uris"]
    assert len(entries) == 3, f"expected 3 manifest entries, got {len(entries)}: {entries}"
    expected_uris = {
        "urn:sbrm:rate:fbt:fy2026:deemed-depreciation-rates",
        "urn:sbrm:rate:fbt:fy2026:benchmark-interest",
        "urn:sbrm:rate:fbt:fy2026:days-in-year",
    }
    assert {e["uri"] for e in entries} == expected_uris
    for entry in entries:
        assert entry["hash_algorithm"] == "sha256"
        assert len(entry["content_hash"]) == 64
        assert all(ch in "0123456789abcdef" for ch in entry["content_hash"])


def test_missing_bundle_surfaces_structured_502(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Defence-in-depth gate: if the bundle is somehow missing in production
    (e.g. a future Dockerfile regression), the route MUST surface a
    structured 502 with an error body, NOT a bare 500 with HTML. This is the
    Lesson #34 anchor — surface, do not paper over.
    """
    monkeypatch.delenv("CLAWDOG_RATE_TABLE_ROOT", raising=False)
    # Point at an empty tmp dir so the resolver finds nothing on disk.
    monkeypatch.setenv("LODGEIT_FBT_REPO", str(tmp_path))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calculate_fbt" and request.method == "POST":
            return httpx.Response(200, json=_mock_dispatch_engine_response())
        if request.url.path == "/health" and request.method == "GET":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404, json={"error": "unmocked route"})

    transport = httpx.MockTransport(handler)
    mock_client = httpx.AsyncClient(transport=transport)

    from api.main import app
    from api.prolog_client import PrologClient
    from api.routes.calculators import get_prolog_client

    async def _override() -> PrologClient:
        return PrologClient(base_url="http://prolog.test", client=mock_client)

    app.dependency_overrides[get_prolog_client] = _override
    try:
        with TestClient(app) as client:
            url = f"/v1/calculators/{quote(CALC_URI, safe='')}/{quote(PERIOD_URI, safe='')}"
            resp = client.post(url, json=PR_D_CASE_5_INPUT)
    finally:
        app.dependency_overrides.pop(get_prolog_client, None)

    assert resp.status_code == 502, (
        f"missing-bundle case must surface 502, got {resp.status_code}: {resp.text[:500]}"
    )
    body = resp.json()
    detail = body.get("detail", {})
    assert isinstance(detail, dict), f"detail must be structured, got: {detail!r}"
    assert detail.get("error") == "manifest_rate_table_unavailable"
    assert "rate_table_root" in detail
    assert "rate_uris" in detail


def test_unratified_taxonomy_rejected_at_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLAWDOG/111 NN#1: taxonomy is a bare atom from the ratified set; an
    unratified value MUST be rejected by the route layer with 422, not
    silently fall through to the resolver or to a path-existence check."""
    monkeypatch.delenv("CLAWDOG_RATE_TABLE_ROOT", raising=False)
    monkeypatch.setenv("LODGEIT_FBT_REPO", str(PRODUCTION_BUNDLE_ROOT))

    from api.main import app

    with TestClient(app) as client:
        url = (
            f"/v1/calculators/{quote(CALC_URI, safe='')}/"
            f"{quote(PERIOD_URI, safe='')}?taxonomy=some_made_up_taxonomy"
        )
        resp = client.post(url, json=PR_D_CASE_5_INPUT)

    assert resp.status_code == 422, (
        f"unratified taxonomy MUST be rejected with 422 per CLAWDOG/111 NN#1, "
        f"got {resp.status_code}: {resp.text[:500]}"
    )
    detail = resp.json().get("detail", "")
    detail_str = detail if isinstance(detail, str) else str(detail)
    assert "ratified" in detail_str.lower() or "some_made_up_taxonomy" in detail_str


__all__ = []
