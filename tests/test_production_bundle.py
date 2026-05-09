"""Production-bundle binary-failure gate.

Phase 3a deemed-dispatch 500 root-cause regression test.

The hermetic E2E suite (`test_phase3a_e2e.py`) sets `CLAWDOG_RATE_TABLE_ROOT`
to a vendored fixture, which short-circuits the production resolver path
(`_rate_table_root_for`). That hermetic green hid a load-bearing defect: the
production Docker image did not bundle the SBRM rate-table tree, so the
production `_rate_table_root_for(period_uri)` resolved to a path that did
not exist (`/srv/lodgeit_fbt/SBRM_RATE_TABLE/fbt/fy2026/`). Any request whose
engine response carried a non-empty `rate_uris_consumed` (i.e. any
deemed-dispatch path) tripped an uncaught `FileNotFoundError` inside
`build_manifest` and surfaced as a bare 500 to the caller.

This gate exercises the **production resolver** against the **production
bundle** (`rate_tables/SBRM_RATE_TABLE/`) shipped inside the Docker image.
It DOES NOT use `CLAWDOG_RATE_TABLE_ROOT`. If this gate is green, the
production manifest path is exercisable.

Per Lesson #25 (Cut-over diff) and Lesson #37 (the runway IS the production
surface), this is the gap the prior test suite was missing: a test that
asserts the live deploy artefact is structurally complete, not just that the
hermetic-mocked code-path is correct.
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


def test_production_bundle_directory_exists() -> None:
    """The production bundle tree must be present in the repo at the path the
    Dockerfile copies into /app/SBRM_RATE_TABLE/."""
    assert PRODUCTION_BUNDLE_ROOT.is_dir(), (
        f"production rate-table bundle missing at {PRODUCTION_BUNDLE_ROOT}; "
        f"the Dockerfile expects to COPY rate_tables/SBRM_RATE_TABLE into the image"
    )
    fy2026 = PRODUCTION_BUNDLE_ROOT / "SBRM_RATE_TABLE" / "fbt" / "fy2026"
    assert fy2026.is_dir(), (
        f"production fy2026 rate-table tree missing at {fy2026}; the manifest "
        f"resolver expects <bundle>/SBRM_RATE_TABLE/<calc>/<period_id>/"
    )


def test_production_bundle_contains_dispatch_rate_tables() -> None:
    """Three rate-table fact-nodes consumed by the deemed-dispatch path MUST
    be present and readable. These are the URIs the engine emits in
    `rate_uris_consumed` when fbt_oc_deemed_dispatch fires."""
    fy2026 = PRODUCTION_BUNDLE_ROOT / "SBRM_RATE_TABLE" / "fbt" / "fy2026"
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


def test_production_resolver_resolves_against_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_rate_table_root_for` resolves to the production bundle when
    LODGEIT_FBT_REPO is wired the way Cloud Run wires it (no
    CLAWDOG_RATE_TABLE_ROOT override)."""
    from api.routes.calculators import _rate_table_root_for

    monkeypatch.delenv("CLAWDOG_RATE_TABLE_ROOT", raising=False)
    monkeypatch.setenv("LODGEIT_FBT_REPO", str(PRODUCTION_BUNDLE_ROOT))

    root = _rate_table_root_for(PERIOD_URI)
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
            url = f"/v1/calculators/{quote(CALC_URI, safe='')}/{quote(PERIOD_URI, safe='')}"
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


__all__ = []
