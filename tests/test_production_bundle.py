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
    # mc17-2026-05-25: required list extended to cover OT #79 (s8a EV
    # exemption) and OT #81 (chained-DV) work that landed on the LodgeiT_FBT
    # engine side and was re-vendored into rate_tables/ in this PR. The list
    # is hand-maintained; a future Tier-B drift gate (banked as a follow-up
    # OT) should derive this from a canonical manifest file shipped alongside
    # the bundle, so a new rate-table on the engine side cannot land here
    # without an explicit re-vendoring step.
    required = [
        "benchmark-interest.md",
        "days-in-year-by-fy.md",        # OT #81 chained-DV (mc17)
        "days-in-year.md",
        "deemed-depreciation-rates.md",
        "fbt-rate.md",
        "gross-up-type-1.md",
        "gross-up-type-2.md",
        "in-house-benefit-cap.md",
        "reasonable-food-allowance.md",
        "rfba-threshold.md",
        "s8a-effective-from.md",                # OT #79 EV exemption (mc17)
        "s8a-lct-low-emission-threshold.md",    # OT #79 EV exemption (mc17)
        "s8a-phev-exclusion-effective-from.md", # OT #79 EV exemption (mc17)
        "statutory-fraction.md",
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


# --- Phase 3c.3.B depreciation production-bundle assertions -----------------
#
# Andrew + Tracer ratified 2026-05-12 05:54 UTC. Mirrors assertion classes #1
# and #2 above against the depreciation calc tree. The end-to-end dispatch
# test is deferred to Phase 3c.4 when the FBT-shaped E2E shape generalises
# into a calc-uri-dispatched test fixture (vs. duplicating the entire body
# below for one extra calculator — Lesson #31 anti-pattern at this scale).

DEPRECIATION_FY2026_PERIOD_URI = "urn:sbrm:period:depreciation:fy2026"

DEPRECIATION_REQUIRED_FILES = [
    "audit-variance-threshold.md",
    "instant-asset-write-off-threshold.md",
    "small-business-pool-rate.md",
]


@pytest.mark.parametrize("taxonomy", RATIFIED_TAXONOMIES)
def test_depreciation_bundle_directory_exists(taxonomy: str) -> None:
    """Assertion class #1 (depreciation): every ratified taxonomy has a
    depreciation bundle directory (populated OR empty-ready)."""
    taxonomy_dir = (
        PRODUCTION_BUNDLE_ROOT / "SBRM_RATE_TABLE" / "depreciation" / taxonomy
    )
    assert taxonomy_dir.is_dir(), (
        f"production depreciation taxonomy bundle directory missing at "
        f"{taxonomy_dir}; the manifest resolver expects "
        f"<bundle>/SBRM_RATE_TABLE/depreciation/<taxonomy>/<period_id>/ "
        f"per CLAWDOG/111 NN#2."
    )


@pytest.mark.parametrize("taxonomy", POPULATED_TAXONOMIES)
def test_depreciation_bundle_contains_audit_rate_tables(taxonomy: str) -> None:
    """Assertion class #2 (depreciation): populated taxonomies carry the
    three rate-table fact-nodes consumed by the audit path."""
    fy2026 = (
        PRODUCTION_BUNDLE_ROOT
        / "SBRM_RATE_TABLE"
        / "depreciation"
        / taxonomy
        / "fy2026"
    )
    for name in DEPRECIATION_REQUIRED_FILES:
        path = fy2026 / name
        assert path.is_file(), f"production depreciation bundle missing {path}"
        text = path.read_text(encoding="utf-8")
        assert "content_hash" in text, f"{path} has no content_hash frontmatter line"


@pytest.mark.parametrize("taxonomy", POPULATED_TAXONOMIES)
def test_depreciation_resolver_resolves_against_bundle(
    monkeypatch: pytest.MonkeyPatch,
    taxonomy: str,
) -> None:
    """Assertion class #3 (depreciation): `rate_table_root_for` resolves to
    a populated depreciation bundle when env is wired Cloud-Run-style."""
    from api.lib.rate_table_resolver import rate_table_root_for

    monkeypatch.delenv("CLAWDOG_RATE_TABLE_ROOT", raising=False)
    monkeypatch.setenv("LODGEIT_FBT_REPO", str(PRODUCTION_BUNDLE_ROOT))

    root = rate_table_root_for(DEPRECIATION_FY2026_PERIOD_URI, taxonomy)
    assert root.is_dir(), f"resolver produced non-existent path {root}"
    assert (root / "audit-variance-threshold.md").is_file()


# --- Phase 4 mut-2026-05-29-mc08 Option-A PR 2: MCP-route + widget-URL --------
#
# SR #12 + Lesson #40 extension: assert that the MCP route renders cleanly
# against the live FastAPI app + that the widget-renderer surface advertised
# by the resolver matches the live deploy URL shape
# (https://lodgeit.org/clawdog-widget-renderer/widgets/<slug>/). The live
# renderer is NOT mocked in this test path; the URL string is asserted to
# match the wire-verified shape captured at mc03-2026-05-29 04:08 UTC.
#
# Lesson #41 honour: assert against the LIVE deploy URL shape, NOT the
# paper-design `widgets.clawdog.io` phrasing from the sprint-design body.


def test_mcp_route_registered_on_production_app() -> None:
    """Assertion class #4 (MCP route registration): /mcp surfaces in the
    OpenAPI spec generated from the production app object.

    The same FastAPI app object is what the Docker image ships; if /mcp is
    NOT in app.routes, the deploy artefact will not surface it either.
    """
    from api.main import app

    # mut-2026-06-19-mc07 SCOPE-CREEP-FIX (NOT part of OT #104 surface):
    # the original test at mut-2026-05-29-mc08 walked `app.routes` directly
    # and read `.path` off each entry. Newer FastAPI/Starlette versions on
    # CI (fastapi 0.137.2 / starlette 1.3.1) hide included-router routes
    # behind `_IncludedRouter` objects in `app.routes` that have neither
    # `.path` nor a public sub-route accessor — walking the route table is
    # version-coupled and brittle.
    #
    # Switch to the OpenAPI spec, which is what the test's docstring
    # actually asserts (*"`/mcp` surfaces in the OpenAPI spec generated
    # from the production app object"*). `app.openapi()` is the public,
    # version-stable contract; if `/mcp` is in the spec, the deploy
    # artefact will surface it. Sibling of Lesson #41 prose-vs-production-
    # code-fidelity (the test wording was always about the OpenAPI spec;
    # the original route-table walk was an implementation accident).
    spec_paths = set(app.openapi().get("paths", {}).keys())
    assert "/mcp" in spec_paths, (
        f"/mcp route missing from production app OpenAPI spec; "
        f"available={sorted(spec_paths)}"
    )


def test_mcp_tools_list_against_production_app_surface() -> None:
    """Assertion class #4 (MCP tools/list): the production FastAPI app
    surfaces the calculator registry as MCP tools.

    Exercises the same in-process surface the Docker image binds; if this
    assertion fails, the deploy will not surface tools either.
    """
    from api.main import app

    client = TestClient(app)
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    tools = body["result"]["tools"]
    assert len(tools) >= 2, (
        f"expected at least 2 MCP tools surfaced from registry; got {len(tools)}"
    )


def test_widget_url_resolver_defaults_to_live_renderer_host() -> None:
    """Assertion class #4 (widget-URL resolver shape):
    ``widget_url_for_calc`` defaults to ``lodgeit.org/clawdog-widget-renderer/
    widgets/<slug>/`` per the live deploy.

    Wire-verified at mc03-2026-05-29 04:08 UTC against
    https://lodgeit.org/clawdog-widget-renderer/widgets/gl-detail-csv-uploader/
    widget.json (HTTP 200, name=gl-detail-csv-uploader).

    Per Lesson #41, the assertion is against the ACTUAL live surface, NOT
    the paper-design ``widgets.clawdog.io`` phrasing from the sprint design.
    """
    from api.services.widget_url_resolver import (
        standalone_widget_url,
        widget_renderer_base_url,
        widget_url_for_calc,
    )

    # NOTE: do NOT use monkeypatch — assert the DEFAULT value (production).
    # We are exercising the production resolver shape per SR #12.
    base = widget_renderer_base_url()
    assert base == "https://lodgeit.org/clawdog-widget-renderer", (
        f"expected production widget-renderer host; got {base!r}"
    )

    fbt_widget = widget_url_for_calc(
        "urn:sbrm:calculator:fbt:car-operating-cost"
    )
    assert fbt_widget == (
        "https://lodgeit.org/clawdog-widget-renderer/widgets/fbt-car-operating-cost/"
    ), f"FBT widget URL drift: got {fbt_widget!r}"

    csv_widget = standalone_widget_url("gl-detail-csv-uploader")
    assert csv_widget == (
        "https://lodgeit.org/clawdog-widget-renderer/widgets/gl-detail-csv-uploader/"
    ), f"CSV widget URL drift: got {csv_widget!r}"


# =============================================================================
# Phase 3a Gross-Up Production-Bundle Gate (mut-2026-06-19-mc07-ot-104)
# =============================================================================
#
# Brain canon authority: clawdog-brain PR #466 (scope; merged 2026-06-19
# 11:22:29Z sha c13cd672) + PR #467 (errata; merged 2026-06-19 11:41:58Z
# sha ae970e11). Engine PR α lodgeit-labs/LodgeiT_FBT #44 merged 2026-06-19
# 11:53:46Z sha 933794a3.
#
# This sprint adds 6 new optional output fields at calc-api response on
# Phase 2l SF + Phase 2l OC:
#   * fbt_type                 ('Type 1' | 'Type 2')
#   * gross_up_factor          (2.0802 for Type 1; 1.8868 for Type 2)
#   * grossed_up_taxable_value (taxable_value * gross_up_factor, 2dp)
#   * fbt_payable              (grossed_up_taxable_value * 0.47, 2dp)
#   * rfba_notional_taxable_value
#   * rfba_notional_grossed_up_t2
#
# Plus a new optional input field on both `FBTCarOperatingCostInput` and
# `FBTCarStatutoryFormulaInput`:
#   * fbtType: Literal["Type 1", "Type 2"] | None
#
# Per SR #12, these tests exercise the PRODUCTION resolver against the
# PRODUCTION bundle (rate_tables/SBRM_RATE_TABLE/), NOT a hermetic fixture.
# The 3 rate-table facts the new arithmetic depends on are vendored at
# rate_tables/SBRM_RATE_TABLE/fbt/lodgeit_au_sbrm/fy2026/{gross-up-type-1,
# gross-up-type-2,fbt-rate}.md and verified by
# test_production_bundle_contains_dispatch_rate_tables above.


CAR_OC_URI = "urn:sbrm:calculator:fbt:car-operating-cost"
CAR_SF_URI = "urn:sbrm:calculator:fbt:car-statutory-formula"


def _mock_oc_gross_up_engine_response(fbt_type: str = "Type 2") -> dict:
    """Mock engine response shape for Phase 2l OC with gross-up arithmetic.

    Mirrors the live engine output dict shape introduced by LodgeiT_FBT PR
    #44 (`mut-2026-06-19-mc06-ot-104-fbt-type-passthrough-gross-up`).
    Numbers are arithmetically consistent with taxable_value=9120 (matches
    Phase 3a `test_phase3a_gross_up_arithmetic.pl` § OC default-Type-2 case).
    """
    if fbt_type == "Type 1":
        gross_up_factor = 2.0802
        grossed_up = round(9120 * 2.0802, 2)  # 18971.42
        fbt_payable = round(grossed_up * 0.47, 2)  # 8916.57
        gross_up_uri = "urn:sbrm:rate:fbt:fy2026:gross-up-type-1"
    else:
        gross_up_factor = 1.8868
        grossed_up = round(9120 * 1.8868, 2)  # 17207.62
        fbt_payable = round(grossed_up * 0.47, 2)  # 8087.58
        gross_up_uri = "urn:sbrm:rate:fbt:fy2026:gross-up-type-2"
    rate_uris = [
        "urn:sbrm:rate:fbt:fy2026:days-in-year",
        gross_up_uri,
        "urn:sbrm:rate:fbt:fy2026:fbt-rate",
    ]
    return {
        "taxable_value": 9120.0,
        "fbt_type": fbt_type,
        "gross_up_factor": gross_up_factor,
        "grossed_up_taxable_value": grossed_up,
        "fbt_payable": fbt_payable,
        "rfba_notional_taxable_value": 9120.0,
        "rfba_notional_grossed_up_t2": round(9120 * 1.8868, 2),
        "rate_uris_consumed": rate_uris,
        "trace": {
            "applied_rate_table_uris": rate_uris,
            "tv_final": 9120.0,
        },
    }


OC_GROSS_UP_INPUT = {
    "leasePayments": 8000,
    "fuelRepairsServicing": 2000,
    "registrationInsurance": 1400,
    "businessUsePercentage": 20,
    "employeeContribution": 0,
    "formOfFinance": "leased",
}


@pytest.mark.parametrize(
    "fbt_type",
    [None, "Type 1", "Type 2"],
    ids=["default_omitted", "explicit_type_1", "explicit_type_2"],
)
def test_oc_gross_up_output_round_trips_through_production_bundle(
    monkeypatch: pytest.MonkeyPatch,
    fbt_type: str | None,
) -> None:
    """Assertion class A (Phase 3a gross-up output surface):

    Phase 2l OC end-to-end gross-up fields round-trip through the calc-api
    response model against the production resolver + production bundle. The
    new output fields appear at the response top level (not in `trace`); the
    pre-mc07 wire shape stays byte-stable in `taxable_value` + `manifest` +
    `advisory`.
    """
    monkeypatch.delenv("CLAWDOG_RATE_TABLE_ROOT", raising=False)
    monkeypatch.setenv("LODGEIT_FBT_REPO", str(PRODUCTION_BUNDLE_ROOT))

    resolved_fbt_type = fbt_type or "Type 2"
    engine_response = _mock_oc_gross_up_engine_response(resolved_fbt_type)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calculate_fbt" and request.method == "POST":
            return httpx.Response(200, json=engine_response)
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
            url = (
                f"/v1/calculators/{quote(CAR_OC_URI, safe='')}/"
                f"{quote(PERIOD_URI, safe='')}?taxonomy=lodgeit_au_sbrm"
            )
            payload = dict(OC_GROSS_UP_INPUT)
            if fbt_type is not None:
                payload["fbtType"] = fbt_type
            resp = client.post(url, json=payload)
    finally:
        app.dependency_overrides.pop(get_prolog_client, None)

    assert resp.status_code == 200, (
        f"OC gross-up surface failed with {resp.status_code}: {resp.text[:500]}"
    )
    body = resp.json()

    # Pre-mc07 wire-shape byte-stability (regression gate).
    assert body["taxable_value"] == pytest.approx(9120.0, abs=0.01)
    assert "manifest" in body and "rate_table_uris" in body["manifest"]
    assert "advisory" in body

    # New mc07 output fields are surfaced at the top level.
    assert body["fbt_type"] == resolved_fbt_type
    expected_factor = 2.0802 if resolved_fbt_type == "Type 1" else 1.8868
    assert body["gross_up_factor"] == pytest.approx(expected_factor, abs=0.0001)
    expected_grossed = round(9120 * expected_factor, 2)
    expected_fbt_payable = round(expected_grossed * 0.47, 2)
    assert body["grossed_up_taxable_value"] == pytest.approx(expected_grossed, abs=0.01)
    assert body["fbt_payable"] == pytest.approx(expected_fbt_payable, abs=0.01)
    assert body["rfba_notional_taxable_value"] == pytest.approx(9120.0, abs=0.01)
    assert body["rfba_notional_grossed_up_t2"] == pytest.approx(
        round(9120 * 1.8868, 2), abs=0.01
    )


def test_oc_gross_up_rate_uris_present_in_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assertion class B (manifest covers gross-up rate-table facts):

    When gross-up arithmetic fires, the 3 consumed rate URIs (gross-up-type-{1
    or 2}, fbt-rate, days-in-year) MUST appear in `manifest.rate_table_uris`
    with valid content-hashes resolved against the production bundle.
    """
    monkeypatch.delenv("CLAWDOG_RATE_TABLE_ROOT", raising=False)
    monkeypatch.setenv("LODGEIT_FBT_REPO", str(PRODUCTION_BUNDLE_ROOT))

    engine_response = _mock_oc_gross_up_engine_response("Type 1")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calculate_fbt" and request.method == "POST":
            return httpx.Response(200, json=engine_response)
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
            url = (
                f"/v1/calculators/{quote(CAR_OC_URI, safe='')}/"
                f"{quote(PERIOD_URI, safe='')}?taxonomy=lodgeit_au_sbrm"
            )
            payload = dict(OC_GROSS_UP_INPUT)
            payload["fbtType"] = "Type 1"
            resp = client.post(url, json=payload)
    finally:
        app.dependency_overrides.pop(get_prolog_client, None)

    assert resp.status_code == 200
    body = resp.json()
    manifest_uris = {e["uri"] for e in body["manifest"]["rate_table_uris"]}
    required = {
        "urn:sbrm:rate:fbt:fy2026:gross-up-type-1",
        "urn:sbrm:rate:fbt:fy2026:fbt-rate",
        "urn:sbrm:rate:fbt:fy2026:days-in-year",
    }
    assert required.issubset(manifest_uris), (
        f"manifest missing gross-up rate URIs: required={required} got={manifest_uris}"
    )
    for entry in body["manifest"]["rate_table_uris"]:
        if entry["uri"] in required:
            assert entry["hash_algorithm"] == "sha256"
            assert len(entry["content_hash"]) == 64


@pytest.mark.parametrize("invalid_value", ["Type 3", "type 1", "Bogus", ""])
def test_oc_invalid_fbt_type_rejected_at_pydantic(
    monkeypatch: pytest.MonkeyPatch,
    invalid_value: str,
) -> None:
    """Assertion class C (Lesson #14 strict-validation at Pydantic layer):

    The Literal["Type 1", "Type 2"] constraint rejects unknown fbtType
    values BEFORE the engine call (cleaner operator error surface than the
    engine's domain_error(fbt_type, _)).
    """
    monkeypatch.delenv("CLAWDOG_RATE_TABLE_ROOT", raising=False)
    monkeypatch.setenv("LODGEIT_FBT_REPO", str(PRODUCTION_BUNDLE_ROOT))

    from api.main import app

    with TestClient(app) as client:
        url = (
            f"/v1/calculators/{quote(CAR_OC_URI, safe='')}/"
            f"{quote(PERIOD_URI, safe='')}?taxonomy=lodgeit_au_sbrm"
        )
        payload = dict(OC_GROSS_UP_INPUT)
        payload["fbtType"] = invalid_value
        resp = client.post(url, json=payload)

    assert resp.status_code == 422, (
        f"expected 422 from Pydantic Literal rejection of fbtType={invalid_value!r}; "
        f"got {resp.status_code}: {resp.text[:300]}"
    )


def test_sf_gross_up_output_round_trips_through_production_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assertion class D (Phase 2l SF symmetric with OC):

    Phase 2l SF gets the same gross-up output surface as OC. mc02
    sheet-parity baseline (case 0: taxable_value=11400 stable at the
    pre-mc07 field).
    """
    monkeypatch.delenv("CLAWDOG_RATE_TABLE_ROOT", raising=False)
    monkeypatch.setenv("LODGEIT_FBT_REPO", str(PRODUCTION_BUNDLE_ROOT))

    grossed_up = round(11400 * 1.8868, 2)  # 21509.52
    fbt_payable = round(grossed_up * 0.47, 2)  # 10109.47
    rate_uris = [
        "urn:sbrm:rate:fbt:fy2026:statutory-fraction",
        "urn:sbrm:rate:fbt:fy2026:days-in-year",
        "urn:sbrm:rate:fbt:fy2026:gross-up-type-2",
        "urn:sbrm:rate:fbt:fy2026:fbt-rate",
    ]
    engine_response = {
        "taxable_value": 11400.0,
        "gross_taxable_value": 11400.0,
        "taxable_value_before_statutory": 11400.0,
        "employee_contribution": 0,
        "reductions": 0,
        "fbt_type": "Type 2",
        "gross_up_factor": 1.8868,
        "grossed_up_taxable_value": grossed_up,
        "fbt_payable": fbt_payable,
        "rfba_notional_taxable_value": 11400.0,
        "rfba_notional_grossed_up_t2": grossed_up,
        "rate_uris_consumed": rate_uris,
        "trace": {"applied_rate_table_uris": rate_uris},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calculate_fbt" and request.method == "POST":
            return httpx.Response(200, json=engine_response)
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
            url = (
                f"/v1/calculators/{quote(CAR_SF_URI, safe='')}/"
                f"{quote(PERIOD_URI, safe='')}?taxonomy=lodgeit_au_sbrm"
            )
            payload = {
                "baseValue": 45000,
                "accessories": 12000,
                "daysAvailable": 365,
                "employeeContribution": 0,
            }
            resp = client.post(url, json=payload)
    finally:
        app.dependency_overrides.pop(get_prolog_client, None)

    assert resp.status_code == 200, resp.text[:500]
    body = resp.json()
    assert body["taxable_value"] == pytest.approx(11400.0, abs=0.01)
    assert body["fbt_type"] == "Type 2"
    assert body["gross_up_factor"] == pytest.approx(1.8868, abs=0.0001)
    assert body["grossed_up_taxable_value"] == pytest.approx(grossed_up, abs=0.01)
    assert body["fbt_payable"] == pytest.approx(fbt_payable, abs=0.01)


def test_other_calculator_response_byte_stable_without_gross_up_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assertion class E (backward-compatibility regression gate):

    Calculators that do not engage the gross-up arithmetic surface (e.g.
    deemed-dispatch OC without fbt_type input) MUST return a response that
    does NOT carry the 6 new fields (they should be absent, not None).
    The pre-mc07 wire-shape is byte-stable for these calculators.
    """
    monkeypatch.delenv("CLAWDOG_RATE_TABLE_ROOT", raising=False)
    monkeypatch.setenv("LODGEIT_FBT_REPO", str(PRODUCTION_BUNDLE_ROOT))

    # Use the pre-mc07 deemed-dispatch engine response (no gross-up fields).
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
            url = (
                f"/v1/calculators/{quote(CALC_URI, safe='')}/"
                f"{quote(PERIOD_URI, safe='')}?taxonomy=lodgeit_au_sbrm"
            )
            resp = client.post(url, json=PR_D_CASE_5_INPUT)
    finally:
        app.dependency_overrides.pop(get_prolog_client, None)

    assert resp.status_code == 200
    body = resp.json()
    # Pre-mc07 wire-shape stable.
    assert body["taxable_value"] == pytest.approx(5547.75, abs=0.01)
    # The 6 new fields are absent (or None) when engine doesn't emit them.
    for new_field in (
        "fbt_type",
        "gross_up_factor",
        "grossed_up_taxable_value",
        "fbt_payable",
        "rfba_notional_taxable_value",
        "rfba_notional_grossed_up_t2",
    ):
        assert body.get(new_field) is None, (
            f"backward-compat regression: {new_field}={body.get(new_field)!r} "
            f"present on response that did not emit gross-up arithmetic"
        )


__all__ = []
