"""D22 mc20 admin probe endpoint tests.

Endpoint: `POST /_internal/probe/engine-auth`.

Fable 2026-09-07 04:19 UTC: *"the fixed #40 must be proven to mint against
a real metadata server before it goes to production traffic — a preview/
tag revision you curl, or a canary on a tag URL — not merged-and-hoped on
green hermetic CI."*

These tests exercise the endpoint's shape + behaviour under mocked mint
paths. The wire-truth capability check is Andrew's post-deploy canary
curl against a --no-traffic tag revision URL; these tests only prove the
endpoint's contract holds hermetically.

Lessons honoured:
    L#37 - endpoint is designed for wire-verification; these tests cover
           its API contract, not the mint capability itself (which cannot
           be tested hermetically).
    L#40 - production-bundle gate covers the deployed surface.
    L#41 - test names describe the contract (per-audience result shape;
           token never leaked in full; both paths named in failure), not
           a spurious "works" claim.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api import prolog_client
from api.routes import internal_auth_probe as probe_module

_PROBE_TOKEN = "canary-secret-abcdef123456"
_PROBE_HEADERS = {"X-Clawdog-Probe-Token": _PROBE_TOKEN}


@pytest.fixture(autouse=True)
def _set_probe_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test in this file needs the probe-token env var set (canary
    posture). Individual tests can override or unset via monkeypatch.
    """
    monkeypatch.setenv("CLAWDOG_ENGINE_AUTH_PROBE_TOKEN", _PROBE_TOKEN)


@pytest.fixture
def client() -> TestClient:
    from api.main import app
    return TestClient(app)


def test_probe_all_ok_when_direct_metadata_mints_all_audiences(client: TestClient) -> None:
    """When direct-metadata mint succeeds for every configured engine,
    endpoint returns all_ok=True + each result names path=direct_metadata.
    Token is truncated to prefix + length (never leaked in full).
    """
    fake_token = "eyJ.header.payload.signature.fake_token_content_at_least_20_chars"
    with patch.object(
        probe_module, "_fetch_id_token_direct_metadata",
        lambda audience: (fake_token, None),
    ):
        resp = client.post("/_internal/probe/engine-auth", json={}, headers=_PROBE_HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    assert body["probe"] == "engine-auth-mint"
    assert body["all_ok"] is True
    assert body["audiences_checked"] == 3  # fbt + depreciation + div7a defaults

    for result in body["results"]:
        assert result["status"] == "OK"
        assert result["path"] == "direct_metadata"
        assert result["token_prefix"] == fake_token[:20]
        assert result["token_length"] == len(fake_token)
        # Never leak the full token.
        assert fake_token not in str(result)
        assert result["direct_metadata_error"] is None


def test_probe_fallback_to_fetch_id_token_when_direct_fails(client: TestClient) -> None:
    """When direct-metadata fails but fetch_id_token succeeds, endpoint
    reports path=fetch_id_token + direct_metadata_error names the direct
    failure. The two-path shape is Fable-mandated per 2026-09-07 04:19 UTC.
    """
    fake_token = "eyJ.fetch.id.token.fallback.works_here_at_least_20"
    with (
        patch.object(prolog_client, "_GOOGLE_AUTH_AVAILABLE", True),
        patch.object(prolog_client, "_GoogleAuthRequest", lambda: object()),
        patch.object(prolog_client, "_google_id_token") as mock_id_token,
        # Patch BOTH names — direct-metadata is called from the probe module
        # (post-import re-bind) AND from prolog_client._authenticated_headers.
        patch.object(
            probe_module, "_fetch_id_token_direct_metadata",
            lambda audience: (None, "host=metadata.google.internal transport=ConnectError: mocked"),
        ),
        patch.object(
            prolog_client, "_fetch_id_token_direct_metadata",
            lambda audience: (None, "host=metadata.google.internal transport=ConnectError: mocked"),
        ),
    ):
        mock_id_token.fetch_id_token.return_value = fake_token
        resp = client.post(
            "/_internal/probe/engine-auth",
            json={"audiences": ["https://fbt-engine-8340695160.australia-southeast1.run.app"]},
            headers=_PROBE_HEADERS,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["all_ok"] is True
    assert body["audiences_checked"] == 1
    result = body["results"][0]
    assert result["status"] == "OK"
    assert result["path"] == "fetch_id_token"
    assert result["token_prefix"] == fake_token[:20]
    assert result["token_length"] == len(fake_token)
    assert "ConnectError" in result["direct_metadata_error"]


def test_probe_reports_fail_when_both_paths_fail(client: TestClient) -> None:
    """When both mint paths fail, endpoint reports all_ok=False + status=FAIL
    per result + names both paths' errors. This is the wire signal Andrew
    reads on the canary URL to know NOT to promote the revision.
    """
    with (
        patch.object(prolog_client, "_GOOGLE_AUTH_AVAILABLE", False),
        patch.object(
            probe_module, "_fetch_id_token_direct_metadata",
            lambda audience: (None, "host=metadata.google.internal transport=ConnectError: no metadata server"),
        ),
        patch.object(
            prolog_client, "_fetch_id_token_direct_metadata",
            lambda audience: (None, "host=metadata.google.internal transport=ConnectError: no metadata server"),
        ),
    ):
        resp = client.post(
            "/_internal/probe/engine-auth",
            json={"audiences": ["https://depreciation-engine-8340695160.australia-southeast1.run.app"]},
            headers=_PROBE_HEADERS,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["all_ok"] is False
    result = body["results"][0]
    assert result["status"] == "FAIL"
    assert result["path"] is None
    assert result["token_prefix"] is None
    assert result["token_length"] is None
    # Reason MUST name both paths so operator sees what's broken.
    assert "all_mint_paths_failed" in result["reason"]


# ---------------------------------------------------------------------------
# Shared-secret gate (Fable 2026-09-07 04:41 UTC note 1)
# ---------------------------------------------------------------------------

def test_probe_returns_404_when_env_var_unset(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production posture: CLAWDOG_ENGINE_AUTH_PROBE_TOKEN env var not
    provisioned → endpoint returns 404 as if it doesn't exist. This is
    how the probe becomes inert when not needed.
    """
    monkeypatch.delenv("CLAWDOG_ENGINE_AUTH_PROBE_TOKEN", raising=False)
    fake_token = "eyJ.should.not.be.reached_at_least_20_chars_ok"
    with patch.object(
        probe_module, "_fetch_id_token_direct_metadata",
        lambda audience: (fake_token, None),
    ):
        resp = client.post("/_internal/probe/engine-auth", json={}, headers=_PROBE_HEADERS)
    assert resp.status_code == 404, (
        f"expected 404 (env-var unset = endpoint invisible); got {resp.status_code}: {resp.text[:200]}"
    )


def test_probe_returns_404_when_header_missing(client: TestClient) -> None:
    """Canary posture with missing header → 404 (not 401). Do not disclose
    endpoint existence to unauthenticated probes.
    """
    fake_token = "eyJ.should.not.be.reached_at_least_20_chars_ok"
    with patch.object(
        probe_module, "_fetch_id_token_direct_metadata",
        lambda audience: (fake_token, None),
    ):
        resp = client.post("/_internal/probe/engine-auth", json={})  # NO headers
    assert resp.status_code == 404


def test_probe_returns_404_when_header_value_mismatched(client: TestClient) -> None:
    """Canary posture with wrong header value → 404 (constant-time compare
    via hmac.compare_digest prevents timing-side-channel disclosure of the
    correct token).
    """
    fake_token = "eyJ.should.not.be.reached_at_least_20_chars_ok"
    with patch.object(
        probe_module, "_fetch_id_token_direct_metadata",
        lambda audience: (fake_token, None),
    ):
        resp = client.post(
            "/_internal/probe/engine-auth",
            json={},
            headers={"X-Clawdog-Probe-Token": "wrong-value-xyz"},
        )
    assert resp.status_code == 404


def test_probe_default_audiences_are_the_three_configured_engines(client: TestClient) -> None:
    """When body has no `audiences`, endpoint uses the three configured
    engine URLs. Verifies the default-audience discovery hasn't drifted
    from the env-var-resolved base URLs.
    """
    fake_token = "eyJ.default.audiences.probe.token_at_least_20_chars_ok"
    audiences_seen: list[str] = []

    def _stub_direct(audience: str):
        audiences_seen.append(audience)
        return fake_token, None

    with patch.object(probe_module, "_fetch_id_token_direct_metadata", _stub_direct):
        resp = client.post("/_internal/probe/engine-auth", json={}, headers=_PROBE_HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    assert body["audiences_checked"] == 3
    # Each result carries the audience URL; probe passed the audience by
    # value to the mint function so we can assert on the seen list.
    assert len(audiences_seen) == 3
    # The 3 configured engines resolve to their default localhost URLs when
    # env vars are unset (test env), which is expected. Just check they're
    # 3 distinct URLs.
    assert len(set(audiences_seen)) == 3
