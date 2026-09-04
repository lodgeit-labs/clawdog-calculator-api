"""Fable Q2 rider mc22 2026-09-04 gate.

Fable verbatim: *"The three depreciation rate-table URIs \u2014 audit-
variance-threshold, instant-asset-write-off-threshold, small-business-
pool-rate \u2014 are advertised in the registry and consumed by nothing.
That is the fiction class this whole PR retires, surviving on a
different surface..."*

*"A README resolves it for the next reader of the repo, not for the
partner developer reading the API. Check whether GET
/v1/rates/{period_uri} enumerates them. If it does, they are
discoverable fiction at the public front door and need the same T6
scope statement Amendment 2 rider 3 put on the depreciation manifest."*

Wire-verified via probe against the deployed gateway 2026-09-04
02:55 UTC: all three URIs return via `GET /v1/rates/urn:sbrm:period:
depreciation:fy2026`. Landed a `scope` annotation on those entries so
a partner developer discovering them at the public front door reads
the same T6 scope statement Amendment 2 rider 3 put on the calc
manifest.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.main import app

PERIOD_URI = "urn:sbrm:period:depreciation:fy2026"
PATH = f"/v1/rates/{quote(PERIOD_URI, safe='')}"

# The three rate IDs that Fable Q2 rider called out.
T6_SCOPED_RATE_IDS = {
    "audit-variance-threshold",
    "instant-asset-write-off-threshold",
    "small-business-pool-rate",
}


@pytest.fixture
def client_with_bundle(monkeypatch, tmp_path) -> TestClient:
    """Point the resolver at the local rate_tables/ tree.

    The default resolver targets `$LODGEIT_FBT_REPO=/srv/lodgeit_fbt`
    which doesn't exist in test. Point it at the repo-local tree.
    """
    # conftest.py's autouse fixture sets CLAWDOG_RATE_TABLE_ROOT to a
    # hermetic Div7A-shaped fixture; that override wins over
    # LODGEIT_FBT_REPO in the resolver. Delete it so we hit the
    # LODGEIT_FBT_REPO branch pointing at the repo-local rate_tables/
    # bundle where the depreciation URIs live.
    monkeypatch.delenv("CLAWDOG_RATE_TABLE_ROOT", raising=False)
    bundle_root = Path(__file__).parent.parent / "rate_tables"
    monkeypatch.setenv("LODGEIT_FBT_REPO", str(bundle_root))
    return TestClient(app)


def test_depreciation_rates_endpoint_returns_scope_annotation_on_t6_urls(
    client_with_bundle: TestClient,
) -> None:
    """Fable Q2 rider mc22 2026-09-04 verbatim gate.

    `GET /v1/rates/{period_uri}` for depreciation MUST annotate each
    entry that names a T6-scoped-but-not-consumed rate table with a
    `scope` field naming the capability and its status. Partner
    developer discovering these at the public front door reads the
    same scope statement Amendment 2 rider 3 put on the calc manifest.
    """
    r = client_with_bundle.get(PATH)
    assert r.status_code == 200, r.text
    body = r.json()
    entries = body["entries"]
    entries_by_id = {e["rate_id"]: e for e in entries}

    # Sanity: the three T6-scoped rate tables are exposed (this is the
    # pre-Fable-Q2-rider state, still true after the fix; the fix
    # annotates them rather than removing them).
    for rate_id in T6_SCOPED_RATE_IDS:
        assert rate_id in entries_by_id, (
            f"Fable Q2 rider probe on 2026-09-04 02:55 UTC saw "
            f"{rate_id} at this endpoint; if it has disappeared, the "
            f"rate-table registry moved. Update this test + the "
            f"annotation set in api/routes/rates.py."
        )

    # Q2 rider fix: every T6-scoped entry carries a `scope` field
    # containing the T6-scope statement.
    for rate_id in T6_SCOPED_RATE_IDS:
        entry = entries_by_id[rate_id]
        scope = entry.get("scope")
        assert scope is not None, (
            f"Fable Q2 rider gate: rate_id={rate_id} is discoverable "
            f"at /v1/rates/{PERIOD_URI} but carries no `scope` field. "
            f"A partner developer discovers this URI and reads it as "
            f"advertised capability. Landed the T6-scope statement in "
            f"api/routes/rates.py `_annotate_t6_scope`."
        )
        # The statement must name pool-retrofit + refusal_class so the
        # partner-developer read matches Amendment 2 \u00a7A2.5.
        assert "T6.1 pool-retrofit" in scope, (
            f"rate_id={rate_id} scope missing pool-retrofit anchor: {scope!r}"
        )
        assert "pool_asset_out_of_t6_scope" in scope, (
            f"rate_id={rate_id} scope missing refusal_class anchor: {scope!r}"
        )


def test_fbt_rates_endpoint_does_not_annotate(
    client_with_bundle: TestClient,
) -> None:
    """Q2 rider fix must be narrow: FBT rate-tables (all consumed by
    live compute) MUST NOT carry the T6-scope annotation.
    """
    fbt_period = "urn:sbrm:period:fbt:fy2026"
    r = client_with_bundle.get(f"/v1/rates/{quote(fbt_period, safe='')}")
    if r.status_code != 200:
        pytest.skip(f"FBT bundle not populated in test env: {r.status_code}")
    body = r.json()
    for entry in body["entries"]:
        assert entry.get("scope") is None, (
            f"FBT rate_id={entry['rate_id']} carried unexpected scope "
            f"annotation. Q2 rider fix must only annotate depreciation "
            f"URIs (v1 pre-registered-but-not-consumed). Got: "
            f"{entry.get('scope')!r}"
        )
