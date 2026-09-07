"""Internal admin probe: attempt to mint an ID token for each configured engine.

D22 mc20 (per Fable 2026-09-07 04:19 UTC).

**Purpose.** Gate the token-mint capability behind a wire-provable check
BEFORE promoting a new gateway revision to production traffic. Fable's
verbatim rule:

  "the fixed #40 must be proven to mint against a real metadata server
   before it goes to production traffic — a preview/tag revision you curl,
   or a canary on a tag URL — not merged-and-hoped on green hermetic CI."

**Design.**

- Endpoint: `POST /_internal/probe/engine-auth`.
- No auth on the endpoint itself (Cloud Run ingress + the deployed URL are
  the only reachability control; the endpoint returns no secrets and mints
  no engine-side calls — just proves the gateway can mint tokens against
  its own identity).
- Body: optional `{"audiences": ["https://x.run.app", ...]}`. When absent,
  the endpoint uses the configured engine URLs from the env-var-resolved
  base URLs (fbt/depreciation/div7a).
- Response: per-audience result including token-mint success (truncated
  token prefix + length, NEVER the full token) + which path succeeded
  (`direct_metadata` / `fetch_id_token`) + per-path error strings on
  failure.
- Never emits the full ID token in the response (only prefix + length +
  path-that-worked); a mint on Cloud Run against IAM-authorised audiences
  proves the capability without leaking a bearer token to whoever hit the
  endpoint.

**Andrew's use pattern (deploy gate):**

1. `gcloud run deploy --tag=canary --no-traffic ...` creates a revision
   available at `https://canary---fbt-calculator-api-<hash>-ts.a.run.app`
   with 0% traffic.
2. `curl -X POST https://canary---fbt-calculator-api-<hash>-ts.a.run.app/_internal/probe/engine-auth` returns per-engine mint results.
3. If all three engines mint successfully: `gcloud run services update-traffic ... --to-tags=canary=100` promotes.
4. If any fail: revision stays at 0% traffic; the JSON response names the
   failure so the fix can iterate WITHOUT touching production.

**What this endpoint deliberately does NOT do:**

- Does not call the engines (just mints tokens; a successful mint doesn't
  prove the engine will accept it, only that the gateway can identify
  itself to the metadata server). The engine-side accept-check is the
  wire-verify curl Andrew runs post-promotion.
- Does not test the IAM binding (mint succeeds even when the SA doesn't
  hold `roles/run.invoker` on the target; the receiving engine's 403 at
  request time is where the binding is verified).
- Does not attempt the mint in an infinite loop or retry (single-shot
  per-audience; caller retries if they want).

Lessons honoured:
    L#37 - endpoint is the wire-provable surface, not another set of mocks.
    L#41 - response honestly declares which path minted the token +
           per-path error strings on failure; no aggregate "OK" that
           hides which of two paths silently no-op'd.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body

from api.prolog_client import (
    EngineAuthUnavailable,
    _authenticated_headers,
    _fetch_id_token_direct_metadata,
    depreciation_prolog_url,
    div7a_engine_url,
    prolog_url,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/_internal/probe", tags=["internal-probe"])


def _configured_engine_audiences() -> list[str]:
    """Return the base URLs of the three engines from env-var resolution."""
    return [prolog_url(), depreciation_prolog_url(), div7a_engine_url()]


def _mint_result_for_audience(audience: str) -> dict:
    """Attempt to mint an ID token for `audience`. Return structured result.

    Never includes the full token in the response — only a prefix (first 20
    chars) + length + which path succeeded. This lets the caller confirm the
    mint worked without exposing a bearer token in whatever they logged the
    response into.
    """
    result: dict = {"audience": audience}

    # Try the direct metadata path FIRST + capture its verdict.
    direct_token, direct_error = _fetch_id_token_direct_metadata(audience)
    if direct_token:
        result.update({
            "status": "OK",
            "path": "direct_metadata",
            "token_prefix": direct_token[:20],
            "token_length": len(direct_token),
            "direct_metadata_error": None,
            "fetch_id_token_error": "not_attempted (direct_metadata succeeded)",
        })
        return result

    result["direct_metadata_error"] = direct_error

    # Try fetch_id_token second via the shared _authenticated_headers path.
    # Wrap in try/except EngineAuthUnavailable so both-paths-failed is
    # captured as a structured response rather than a 500.
    try:
        headers = _authenticated_headers(audience)
    except EngineAuthUnavailable as exc:
        result.update({
            "status": "FAIL",
            "path": None,
            "token_prefix": None,
            "token_length": None,
            "fetch_id_token_error": str(exc),
            "reason": exc.reason,
        })
        return result

    # If _authenticated_headers returned {} for a Cloud Run audience we'd
    # never be here (it now raises EngineAuthUnavailable). But defensively:
    if not headers:
        result.update({
            "status": "FAIL",
            "path": None,
            "token_prefix": None,
            "token_length": None,
            "fetch_id_token_error": "returned_empty_dict_on_cloud_run_audience",
            "reason": "unreachable_soft_mode_on_cloud_run",
        })
        return result

    # fetch_id_token succeeded (direct_metadata failed above).
    token = headers["Authorization"].split(" ", 1)[1]
    result.update({
        "status": "OK",
        "path": "fetch_id_token",
        "token_prefix": token[:20],
        "token_length": len(token),
        "fetch_id_token_error": None,
    })
    return result


@router.post(
    "/engine-auth",
    summary="D22 mc20 admin probe: prove gateway can mint ID tokens for engine audiences.",
    description=(
        "Attempts to mint an ID token for each configured engine URL (or the "
        "audiences supplied in the body). Returns per-audience status naming "
        "which mint path succeeded (direct_metadata vs fetch_id_token) + "
        "per-path error strings on failure. Token itself is NOT returned in "
        "full (only prefix + length) to avoid leaking a bearer through "
        "response logs.\n\n"
        "**Deploy gate use:** curl this against a canary/tag revision URL "
        "BEFORE promoting the revision to production traffic. If any engine "
        "mint fails, the revision stays at 0% traffic and the failure log "
        "guides the fix without impacting live callers. Fable's rule: "
        "\"the fixed #40 must be proven to mint against a real metadata "
        "server before it goes to production traffic.\""
    ),
)
async def probe_engine_auth(
    body: dict | None = Body(default=None),
) -> dict:
    """Probe endpoint. Returns per-audience mint results."""
    audiences = (body or {}).get("audiences")
    if not audiences:
        audiences = _configured_engine_audiences()

    results = [_mint_result_for_audience(a) for a in audiences]

    return {
        "probe": "engine-auth-mint",
        "audiences_checked": len(results),
        "all_ok": all(r["status"] == "OK" for r in results),
        "results": results,
    }
