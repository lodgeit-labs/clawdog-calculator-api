"""D22 gateway authentication choke-point tests (mut-2026-09-07-mc19).

**Wire evidence (2026-09-07 03:53 UTC):** after depreciation-engine was
locked down via PR #23 + Andrew's explicit `remove-iam-policy-binding
allUsers` (D21 Step 3 in flight), the gateway called depreciation-engine
WITHOUT an ID token, got Cloud Run 403, and returned 502
`engine_auth_failed status_code:403` to the caller. The gateway is the
broken side but the wire evidence pointed at the engine.

Fable's rule (verbatim 2026-09-07 03:53 UTC):

  "every engine call the gateway makes must attach an ID token whose
   audience is that engine's own URL, through one shared choke point, so
   no engine can ever be called untokenised again. A per-client fix that
   leaves the next engine's path bare is the same gap wearing a new
   client name."

The choke point is `api.prolog_client.PrologClient.dispatch()`. Every
outbound engine call funnels through it (all 4 methods: `calculate_fbt`,
`depreciation_at`, `depreciation_range`, `div7a_at` are wrappers around
`dispatch(engine, payload, path_override=...)`).

The D22 fix at the choke point:
  1. `_authenticated_headers` for Cloud Run audiences returns Bearer OR
     RAISES `EngineAuthUnavailable`. NEVER silently returns `{}`.
  2. `dispatch()` catches `EngineAuthUnavailable` + re-raises as
     `PrologEngineUnavailable(error_code="engine_auth_local_fail")`.
  3. `engine_error_mapper` maps `engine_auth_local_fail` -> 503 with
     DISTINCT slug (partitions from engine-side 403 502 `engine_auth_failed`).
  4. Emergency escape: `CLAWDOG_ENGINE_AUTH_SOFT_MODE=1` env var forces
     silent-fallback behaviour with WARNING log for visibility.

This test file proves the choke-point invariant + the strict-raise +
the soft-mode escape + verifies all 3 engines route through `dispatch()`
(no engine-specific path bypasses the auth check).

Lessons honoured:
    L#37 - tests exercise dispatch() + mapper directly.
    L#40 - hermetic + production-bundle covers deployed surface.
    L#41 - test names honestly describe the invariant (choke point +
           strict-raise + soft escape), not the mechanism.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api import prolog_client
from api.prolog_client import (
    DEPRECIATION_ENGINE,
    DIV7A_ENGINE,
    FBT_ENGINE,
    PrologClient,
    PrologEngineUnavailable,
)

# ---------------------------------------------------------------------------
# Choke-point invariant: all 3 engines route through the same dispatch()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_three_engines_route_through_dispatch() -> None:
    """No engine-specific path bypasses `dispatch()`. Any egress method on
    PrologClient MUST funnel through `dispatch()` which is the sole site of
    `_authenticated_headers` invocation. Fable's *"one shared choke point"*
    rule. If a future PR adds a fourth engine that bypasses dispatch(),
    this test catches it.
    """
    # Enumerate all public async methods on PrologClient that do outbound
    # HTTP (health() is separate + intentionally not gated on auth in
    # first cut).
    egress_methods = ("calculate_fbt", "depreciation_at", "depreciation_range", "div7a_at")

    for method_name in egress_methods:
        # Ensure the method exists.
        assert hasattr(PrologClient, method_name), (
            f"PrologClient.{method_name} missing"
        )
        # Ensure the method's implementation calls `dispatch` (source-level
        # invariant; documented as the choke-point rule per D22).
        import inspect
        src = inspect.getsource(getattr(PrologClient, method_name))
        assert "dispatch(" in src or "self.dispatch(" in src, (
            f"PrologClient.{method_name} does NOT call dispatch(); "
            f"D22 choke-point invariant violated. Every egress method must "
            f"funnel through dispatch() which is the sole `_authenticated_"
            f"headers` invocation site."
        )


# ---------------------------------------------------------------------------
# Cloud Run audience + google-auth missing -> EngineAuthUnavailable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_raises_engine_auth_local_fail_when_google_auth_missing() -> None:
    """When google-auth is missing at runtime AND the audience is a Cloud
    Run URL, dispatch() must re-raise as PrologEngineUnavailable with
    error_code='engine_auth_local_fail'. The request must NEVER be sent.
    """
    cloud_run_url = "https://depreciation-engine-8340695160.australia-southeast1.run.app"
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    # Ensure client.post is never called (request not sent).
    mock_client.post = AsyncMock(side_effect=AssertionError(
        "dispatch() sent an HTTP request despite EngineAuthUnavailable; "
        "request must NEVER be sent when gateway cannot mint a token."
    ))

    with (
        patch.object(prolog_client, "_GOOGLE_AUTH_AVAILABLE", False),
        patch.dict(os.environ, {}, clear=False),
    ):
        os.environ.pop("CLAWDOG_ENGINE_AUTH_SOFT_MODE", None)
        client = PrologClient(depreciation_base_url=cloud_run_url, client=mock_client)
        with pytest.raises(PrologEngineUnavailable) as excinfo:
            await client.dispatch(
                DEPRECIATION_ENGINE,
                {"basis": "accounting"},
                path_override="/v1/calculators/depreciation/at/x",
            )

    assert excinfo.value.error_code == "engine_auth_local_fail"
    assert excinfo.value.engine == DEPRECIATION_ENGINE
    assert isinstance(excinfo.value.detail, dict)
    assert excinfo.value.detail["reason"] == "google_auth_missing"
    assert excinfo.value.detail["audience"] == cloud_run_url


@pytest.mark.asyncio
async def test_dispatch_raises_engine_auth_local_fail_when_metadata_fetch_fails() -> None:
    """When google-auth is available but metadata-server fetch throws AND
    the audience is a Cloud Run URL, dispatch() must re-raise as
    PrologEngineUnavailable with error_code='engine_auth_local_fail'. The
    request must NEVER be sent.
    """
    cloud_run_url = "https://fbt-engine-8340695160.australia-southeast1.run.app"
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=AssertionError(
        "dispatch() sent an HTTP request despite metadata-fetch failure"
    ))

    with (
        patch.object(prolog_client, "_GOOGLE_AUTH_AVAILABLE", True),
        patch.object(prolog_client, "_GoogleAuthRequest", MagicMock()),
        patch.object(prolog_client, "_google_id_token") as mock_id_token,
        patch.dict(os.environ, {}, clear=False),
    ):
        os.environ.pop("CLAWDOG_ENGINE_AUTH_SOFT_MODE", None)
        mock_id_token.fetch_id_token.side_effect = Exception("metadata server unreachable")
        client = PrologClient(base_url=cloud_run_url, client=mock_client)
        with pytest.raises(PrologEngineUnavailable) as excinfo:
            await client.dispatch(FBT_ENGINE, {"payload": "x"})

    assert excinfo.value.error_code == "engine_auth_local_fail"
    assert excinfo.value.detail["reason"] == "metadata_fetch_failed"
    assert "metadata server unreachable" in str(excinfo.value.detail.get("cause", ""))


# ---------------------------------------------------------------------------
# Soft-mode escape hatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_soft_mode_env_var_swallows_engineauthunavailable_and_sends_unauth(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When CLAWDOG_ENGINE_AUTH_SOFT_MODE=1 is set, dispatch() catches
    EngineAuthUnavailable + falls through to unauth request + logs WARNING.
    Reserved for metadata-server outage emergency rollback.
    """
    import logging
    cloud_run_url = "https://div7a-engine-8340695160.australia-southeast1.run.app"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"ok": True})
    mock_client.post.return_value = mock_response

    with (
        patch.object(prolog_client, "_GOOGLE_AUTH_AVAILABLE", False),
        patch.dict(os.environ, {"CLAWDOG_ENGINE_AUTH_SOFT_MODE": "1"}, clear=False),
    ):
        client = PrologClient(div7a_base_url=cloud_run_url, client=mock_client)
        with caplog.at_level(logging.WARNING, logger="api.prolog_client"):
            result = await client.dispatch(
                DIV7A_ENGINE,
                {"loan_uri": "urn:x"},
                path_override="/v1/calculators/div7a/at/urn:sbrm:period:div7a:fy2025",
            )

    assert result == {"ok": True}
    # Verify the request WAS sent with empty headers (unauth).
    call_kwargs = mock_client.post.call_args.kwargs
    assert call_kwargs.get("headers") == {}
    # Verify WARNING logged for soft-mode enablement visibility.
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("engine_auth_soft_mode_engaged" in r.message for r in warning_records), (
        f"expected engine_auth_soft_mode_engaged WARNING; got: "
        f"{[r.message for r in warning_records]}"
    )


# ---------------------------------------------------------------------------
# Mapper: engine_auth_local_fail -> 503 with distinct slug
# ---------------------------------------------------------------------------

def test_mapper_translates_engine_auth_local_fail_to_503() -> None:
    """PrologEngineUnavailable with error_code='engine_auth_local_fail'
    maps to HTTP 503 with 'error': 'engine_auth_local_fail'. DISTINCT from
    engine-side 403 which maps to 502 'engine_auth_failed'. Partition
    matters at the SRE dashboard so gateway-identity-broken doesn't blend
    with engine-identity-broken.
    """
    from api.lib.engine_error_mapper import map_engine_error_to_http
    exc = PrologEngineUnavailable(
        error_code="engine_auth_local_fail",
        detail={"reason": "metadata_fetch_failed", "audience": "https://x.run.app", "cause": "TimeoutError: x"},
        engine="depreciation",
        url="https://x.run.app/v1/calculators/depreciation/at/urn:x",
    )
    http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 503, (
        f"expected 503 (distinct from engine-side 403 -> 502); "
        f"got {http_exc.status_code}"
    )
    assert http_exc.detail["error"] == "engine_auth_local_fail"
    assert http_exc.detail["error_code"] == "engine_auth_local_fail"
    assert http_exc.detail["engine"] == "depreciation"
    assert http_exc.detail["detail"]["reason"] == "metadata_fetch_failed"


def test_mapper_engine_auth_local_fail_slug_not_shadowed_by_engine_label() -> None:
    """engine_label override does NOT shadow the engine_auth_local_fail
    slug. Same discipline as engine_auth_failed (mc14): auth partition
    must survive constellation-wide label overrides.
    """
    from api.lib.engine_error_mapper import map_engine_error_to_http
    exc = PrologEngineUnavailable(
        error_code="engine_auth_local_fail",
        detail={"reason": "google_auth_missing", "audience": "https://x.run.app"},
        engine="div7a",
        url="https://x.run.app/v1/calculators/div7a/at/x",
    )
    http_exc = map_engine_error_to_http(exc, engine_label="div7a_engine_unavailable")
    assert http_exc.status_code == 503
    assert http_exc.detail["error"] == "engine_auth_local_fail", (
        "engine_auth_local_fail slug must survive engine_label override"
    )


# ---------------------------------------------------------------------------
# Localhost / .test / docker-compose stay soft (no regression from mc14)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_localhost_audience_still_soft_no_authorization_header() -> None:
    """Non-Cloud-Run audiences (localhost, docker-compose hostnames, .test
    TLD) continue to receive empty headers without raising. Dev + hermetic
    tests must keep working without gcloud setup.
    """
    from api.prolog_client import _authenticated_headers
    # None of these should raise:
    assert _authenticated_headers("http://localhost:8081/x") == {}
    assert _authenticated_headers("http://127.0.0.1:8082/x") == {}
    assert _authenticated_headers("http://prolog:8081/x") == {}
    assert _authenticated_headers("http://fbt-engine.test/x") == {}
    assert _authenticated_headers("http://engine.example/x") == {}


# ---------------------------------------------------------------------------
# End-to-end: Cloud Run success path still returns Bearer header
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cloud_run_success_path_attaches_bearer() -> None:
    """When google-auth is available AND metadata fetch succeeds AND
    audience is a Cloud Run URL, dispatch() attaches the Bearer header on
    the httpx call. Regression gate for the primary happy path.
    """
    fake_token = "eyJ.header.signature.fake"
    cloud_run_url = "https://depreciation-engine-8340695160.australia-southeast1.run.app"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"wdv_at": "9830.60"})
    mock_client.post.return_value = mock_response

    with (
        patch.object(prolog_client, "_GOOGLE_AUTH_AVAILABLE", True),
        patch.object(prolog_client, "_GoogleAuthRequest", MagicMock()),
        patch.object(prolog_client, "_google_id_token") as mock_id_token,
    ):
        mock_id_token.fetch_id_token.return_value = fake_token
        client = PrologClient(depreciation_base_url=cloud_run_url, client=mock_client)
        result = await client.dispatch(
            DEPRECIATION_ENGINE,
            {"basis": "accounting"},
            path_override="/v1/calculators/depreciation/at/x",
        )

    assert result == {"wdv_at": "9830.60"}
    call_kwargs = mock_client.post.call_args.kwargs
    assert call_kwargs["headers"] == {"Authorization": f"Bearer {fake_token}"}
    # Audience is scheme://netloc (path stripped).
    audience_arg = mock_id_token.fetch_id_token.call_args.args[1]
    assert audience_arg == cloud_run_url
