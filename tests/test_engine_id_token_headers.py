"""Hermetic tests for the engine ID-token header helper introduced under
mc14-2026-09-06 (Engine lock-down Step 1 per Fable 2026-09-06 UTC).

The helper (`api.prolog_client._authenticated_headers`) attaches a Cloud
Run ID token to every outbound engine call when the audience is a Cloud
Run URL, and returns `{}` on localhost / docker-compose / test URLs so
local dev + hermetic tests don't have to authenticate against a metadata
server that isn't there.

Coverage:
  - localhost audience              → empty dict (no token)
  - 127.0.0.1 audience              → empty dict
  - docker-compose service hostname → empty dict
  - Cloud Run URL when google-auth AVAILABLE + metadata fetch succeeds
    → {"Authorization": "Bearer <token>"}, audience = scheme://netloc
  - Cloud Run URL when google-auth AVAILABLE + metadata fetch fails
    → empty dict + warning log (best-effort emission)
  - Cloud Run URL when google-auth NOT installed
    → empty dict
  - dispatch() attaches header to httpx.post call
    (integration-shape hermetic test with mocked client)

Lessons honoured:
  #37 — tests exercise the helper directly (the production interface)
         plus the dispatch() integration point; not paraphrased.
  #40 — production-bundle gate covers deployed-URL surface separately.
  #35 — 8 tests / mechanically enforced / pytest exit is the gate.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api import prolog_client
from api.prolog_client import (
    FBT_ENGINE,
    PrologClient,
    _authenticated_headers,
    _is_localhost_audience,
)

# ---------------------------------------------------------------------------
# _is_localhost_audience
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("http://localhost:8081/calculate_fbt", True),
    ("http://localhost:8082", True),
    ("http://127.0.0.1:8082/x", True),
    ("http://127.1.1.1/x", True),
    ("http://0.0.0.0:8083", True),
    # docker-compose service hostnames
    ("http://prolog:8081/calculate_fbt", True),
    ("http://depreciation:8082/x", True),
    ("http://div7a:8083/x", True),
    ("http://fbt-engine:8080/x", True),
    ("http://depreciation-engine:8080/x", True),
    ("http://div7a-engine:8080/x", True),
    # Real Cloud Run URLs
    ("https://fbt-engine-8340695160.australia-southeast1.run.app/calculate_fbt", False),
    ("https://div7a-engine-8340695160.australia-southeast1.run.app/v1/x", False),
    ("https://depreciation-engine-8340695160.australia-southeast1.run.app/x", False),
])
def test_is_localhost_audience(url: str, expected: bool) -> None:
    assert _is_localhost_audience(url) is expected


def test_is_localhost_audience_unparseable_defaults_to_true() -> None:
    # Malformed / unparseable URL → err on side of no token
    assert _is_localhost_audience("") is True


# ---------------------------------------------------------------------------
# _authenticated_headers
# ---------------------------------------------------------------------------

def test_authenticated_headers_localhost_returns_empty() -> None:
    assert _authenticated_headers("http://localhost:8081/calculate_fbt") == {}


def test_authenticated_headers_docker_compose_returns_empty() -> None:
    assert _authenticated_headers("http://prolog:8081/calculate_fbt") == {}


def test_authenticated_headers_google_auth_unavailable_raises_engineauthunavailable() -> None:
    """D22 mc20 update (per Fable 2026-09-07 04:19 UTC): both mint paths
    (direct_metadata + fetch_id_token) must fail before EngineAuthUnavailable
    is raised. When google-auth is not importable AND direct-metadata call
    times out / connects nowhere AND the audience is a Cloud Run URL, the
    helper raises `EngineAuthUnavailable(reason="all_mint_paths_failed: ...")`.

    Prior mc19 shape had a single fetch_id_token path with reason=
    "google_auth_missing"; mc20 shape has two paths per Fable's ruling that
    fetch_id_token doesn't work on Cloud Run in the general case; direct
    metadata call is primary. Reason now aggregates both paths' errors.
    """
    from api.prolog_client import EngineAuthUnavailable
    with (
        patch.object(prolog_client, "_GOOGLE_AUTH_AVAILABLE", False),
        # Stub direct metadata to fail cleanly (no live metadata server on
        # the sandbox); on real Cloud Run the direct path succeeds first.
        patch.object(
            prolog_client, "_fetch_id_token_direct_metadata",
            lambda audience: (None, "host=metadata.google.internal transport=ConnectError: mocked"),
        ),
    ):
        with pytest.raises(EngineAuthUnavailable) as excinfo:
            _authenticated_headers(
                "https://fbt-engine-8340695160.australia-southeast1.run.app/calculate_fbt"
            )
    assert "all_mint_paths_failed" in excinfo.value.reason
    assert "direct_metadata" in excinfo.value.reason
    assert "fetch_id_token" in excinfo.value.reason
    assert "google_auth_missing" in excinfo.value.reason
    assert excinfo.value.audience == "https://fbt-engine-8340695160.australia-southeast1.run.app"


def test_authenticated_headers_google_auth_unavailable_still_soft_on_localhost() -> None:
    """Soft-mode is preserved for localhost even when google-auth is absent.
    Dev-loop ergonomics require dev boxes without gcloud auth to still work
    against http://localhost:* engines.
    """
    with patch.object(prolog_client, "_GOOGLE_AUTH_AVAILABLE", False):
        assert _authenticated_headers("http://localhost:8081/calculate_fbt") == {}
        assert _authenticated_headers("http://prolog:8081/calculate_fbt") == {}
        assert _authenticated_headers("http://fbt-engine.test/calculate_fbt") == {}


def test_authenticated_headers_cloud_run_url_fetches_token() -> None:
    """When google-auth is available AND audience is Cloud Run, the helper
    fetches an ID token via the metadata server + returns it as a Bearer
    header. Audience is the scheme://netloc form (path stripped).
    """
    fake_token = "eyJhbGciOiJSUzI1NiJ9.fake-token-payload.fake-sig"
    with (
        patch.object(prolog_client, "_GOOGLE_AUTH_AVAILABLE", True),
        patch.object(prolog_client, "_GoogleAuthRequest", MagicMock()),
        patch.object(prolog_client, "_google_id_token") as mock_id_token,
    ):
        mock_id_token.fetch_id_token.return_value = fake_token
        result = _authenticated_headers(
            "https://fbt-engine-8340695160.australia-southeast1.run.app/calculate_fbt"
        )

    assert result == {"Authorization": f"Bearer {fake_token}"}
    # Audience passed to fetch_id_token strips the path
    call_args = mock_id_token.fetch_id_token.call_args
    assert call_args.args[1] == "https://fbt-engine-8340695160.australia-southeast1.run.app"


def test_authenticated_headers_both_mint_paths_fail_raises_engineauthunavailable_and_logs_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """D22 mc20 update (per Fable 2026-09-07 04:19 UTC): when BOTH mint
    paths fail (direct metadata + fetch_id_token), the helper RAISES
    `EngineAuthUnavailable` with an aggregated reason naming both paths'
    errors + logs at ERROR level.

    Prior mc19 shape had a single fetch_id_token path with reason=
    "metadata_fetch_failed"; mc20 shape has two paths, so the reason string
    aggregates both. On real Cloud Run, the direct-metadata path is
    expected to succeed first (Fable's prior 2026-09-07 04:19 UTC).
    """
    from api.prolog_client import EngineAuthUnavailable
    with (
        patch.object(prolog_client, "_GOOGLE_AUTH_AVAILABLE", True),
        patch.object(prolog_client, "_GoogleAuthRequest", MagicMock()),
        patch.object(prolog_client, "_google_id_token") as mock_id_token,
        patch.object(
            prolog_client, "_fetch_id_token_direct_metadata",
            lambda audience: (None, "host=metadata.google.internal transport=ConnectError: mocked_sandbox"),
        ),
    ):
        mock_id_token.fetch_id_token.side_effect = Exception("fetch_id_token also unreachable")
        with caplog.at_level(logging.ERROR, logger="api.prolog_client"):
            with pytest.raises(EngineAuthUnavailable) as excinfo:
                _authenticated_headers(
                    "https://fbt-engine-8340695160.australia-southeast1.run.app/x"
                )

    assert "all_mint_paths_failed" in excinfo.value.reason
    assert "direct_metadata" in excinfo.value.reason
    assert "fetch_id_token" in excinfo.value.reason
    assert "mocked_sandbox" in excinfo.value.reason
    assert "fetch_id_token also unreachable" in excinfo.value.reason
    assert excinfo.value.audience == "https://fbt-engine-8340695160.australia-southeast1.run.app"

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) == 1, (
        f"expected exactly 1 ERROR log, got {len(error_records)}"
    )
    assert "engine_id_token_fetch_failed" in error_records[0].message
    assert "attempts=" in error_records[0].message


# ---------------------------------------------------------------------------
# dispatch() integration: header is attached to httpx.post call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_attaches_id_token_header_when_cloud_run() -> None:
    """dispatch() calls _authenticated_headers(url) and forwards the result
    into httpx.AsyncClient.post(..., headers=...). With a Cloud Run
    audience + mocked google-auth, the header dict must be non-empty and
    reach the client.
    """
    fake_token = "eyJhbGciOiJSUzI1NiJ9.fake-token.fake-sig"
    engine_url = "https://fbt-engine-8340695160.australia-southeast1.run.app"

    # Mock httpx client that captures the call
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"grossed_up_taxable_value": 100.0})
    mock_client.post.return_value = mock_response

    with (
        patch.object(prolog_client, "_GOOGLE_AUTH_AVAILABLE", True),
        patch.object(prolog_client, "_GoogleAuthRequest", MagicMock()),
        patch.object(prolog_client, "_google_id_token") as mock_id_token,
    ):
        mock_id_token.fetch_id_token.return_value = fake_token
        client = PrologClient(base_url=engine_url, client=mock_client)
        await client.dispatch(FBT_ENGINE, {"payload": "x"})

    # Verify header made it into the .post call
    call_kwargs = mock_client.post.call_args.kwargs
    assert "headers" in call_kwargs
    assert call_kwargs["headers"] == {"Authorization": f"Bearer {fake_token}"}


@pytest.mark.asyncio
async def test_dispatch_omits_authorization_header_when_localhost() -> None:
    """When engine URL is localhost (hermetic test / dev), dispatch() must
    NOT attach an Authorization header (metadata server won't respond).
    """
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"ok": True})
    mock_client.post.return_value = mock_response

    client = PrologClient(base_url="http://localhost:8081", client=mock_client)
    await client.dispatch(FBT_ENGINE, {"payload": "x"})

    call_kwargs = mock_client.post.call_args.kwargs
    assert call_kwargs.get("headers") == {}
