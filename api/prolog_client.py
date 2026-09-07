"""HTTP client for upstream Prolog calculator engines.

Reaches the Prolog substrates and returns each engine's native
``DictOut`` shape unchanged. The bridge layer above (``api.routes``)
adds the manifest and advisory blocks; this client is bare transport.

Per CLAWDOG/109 §3.2, the direct-Prolog HTTP surface is the *truth-ground*.
This client treats it as such — no schema reshaping, no field renaming, no
silent fallbacks. Each engine's response is opaque JSON in transit; the
calling route reads the fields it needs and surfaces the rest unchanged.

Phase 3c.3.B (`mut-2026-05-12` post-PR #170) onboards depreciation via
the minimum-viable option α (Andrew + Tracer ratified 2026-05-12 05:54 UTC).
The FBT-shaped surface stays as-is; depreciation is added as a sibling
method with its own engine URL env var. Phase 3c.4 will generalise this
into a single ``(calc_uri, method) → (base_url, path)`` resolver and close
the abstraction leak surfaced by CLAWDOG/109 §8.3 during the firing
reconnaissance.

Phase 3c.4 Option-C PR α (`mut-2026-05-28-mc06`; Andrew direct-voice ratified
2026-05-28 10:34 UTC) introduces ``PrologClient.dispatch()`` — a single
entry point that catches ``httpx.ConnectError | httpx.HTTPError | httpx.
TimeoutException`` in addition to the existing ``PrologCalculationError``
path, mapping all transport-layer failures to a new ``PrologEngineUnavailable``
exception. Both calling routes (FBT car operating-cost + depreciation audit)
map ``PrologEngineUnavailable`` to a structured 502/503 response, closing
the Standing Rule #12 clause (e) violation on the depreciation route (the
bare HTML 500 root cause: production deploy has no ``DEPRECIATION_PROLOG_URL``
env var, so requests fall through to ``localhost:8082`` and throw an uncaught
``httpx.ConnectError``; wire-verified 2026-05-28 06:05 UTC + 10:30 UTC). The
fix is defence-in-depth: if the FBT engine ever became unreachable, the same
catch protects the FBT route from the symmetric bare-500 failure mode.

The existing ``calculate_fbt()`` + ``depreciation_at()`` methods are kept
as thin wrappers calling ``dispatch()`` for backward compatibility with
existing tests. Route-handler unification (collapsing the two routes into a
single ``invoke_calculator`` with discriminated-union body type) is
DEFERRED to a future PR when a third calculator surfaces — per Lesson #31
the two routes have zero schema overlap today and forcing them into one
shape ahead of n=2 signal would be premature design.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Engine lock-down Step 1 (mut-2026-09-06-mc14 per Fable 2026-09-06 UTC).
# On Cloud Run, every engine call carries an ID token whose audience is the
# engine's URL. On the engine side, Cloud Run's built-in IAM check validates
# the token + confirms the caller SA holds roles/run.invoker before the
# request reaches user code. Local dev + docker-compose bypass via a
# localhost audience discriminator (metadata server won't respond there).
#
# `google-auth` is a soft optional import: if not installed OR if metadata
# fetch fails at request time OR if audience is localhost, the header dict
# is empty and the request goes out unauthenticated. Cloud Run 403 is the
# authority; header emission is best-effort. This preserves local-dev
# ergonomics (no gcloud auth required) while enforcing prod behaviour via
# the engine-side IAM gate rather than gateway-side pre-flight.
try:
    from google.auth.transport.requests import Request as _GoogleAuthRequest
    from google.oauth2 import id_token as _google_id_token
    _GOOGLE_AUTH_AVAILABLE = True
except ImportError:  # pragma: no cover — google-auth is a hard dep on Cloud Run
    _GOOGLE_AUTH_AVAILABLE = False
    _GoogleAuthRequest = None  # type: ignore[assignment,misc]
    _google_id_token = None  # type: ignore[assignment]

# D22 real-metadata mint (mut-2026-09-07-mc20 per Fable 2026-09-07 04:19 UTC).
#
# Fable's strong prior verbatim: *"google.oauth2.id_token.fetch_id_token(request,
# audience) does not mint for the attached service account on Cloud Run in the
# general case; the working paths are a direct metadata call to …/service-
# accounts/default/identity?audience=<url> with Metadata-Flavor: Google, or
# google.auth.compute_engine.IDTokenCredentials."*
#
# mc19 relied solely on fetch_id_token. Wire evidence 2026-09-07 04:19 UTC: it
# never worked in the deployed runtime. mc14's silent fallback masked that
# because engines were still allUsers-invoker-bound; mc19's strict-raise
# exposed the underlying capability defect the moment it shipped.
#
# mc20 fix: try DIRECT metadata call first (Fable's primary path), fall back to
# fetch_id_token second. The direct metadata call is the wire-authoritative
# form documented at:
#   https://cloud.google.com/run/docs/securing/service-identity#identity_tokens
# using the Cloud Run metadata server at metadata.google.internal (or IP
# 169.254.169.254). Uses httpx (already a dep) so no new imports required.
_METADATA_HOSTS = ("metadata.google.internal", "169.254.169.254")
_METADATA_HEADER = {"Metadata-Flavor": "Google"}
_METADATA_TIMEOUT = httpx.Timeout(3.0, connect=2.0)  # fail fast on non-GCE
_METADATA_ID_TOKEN_PATH = "/computeMetadata/v1/instance/service-accounts/default/identity"

DEFAULT_PROLOG_URL = "http://localhost:8081"
DEFAULT_DEPRECIATION_URL = "http://localhost:8082"
# Phase D (mut-2026-08-24-mc20): Div7A_Engine gateway routing. Div7A_Engine
# speaks native FastAPI (not Prolog HTTP), but the PrologClient's dispatch
# abstraction is the constellation's canonical external-engine transport
# entry point per L#28 single-concern. Naming preserved for consistency;
# behaviour is HTTP JSON round-trip regardless of downstream engine tech.
DEFAULT_DIV7A_URL = "http://localhost:8083"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)

# Engine identifiers for ``PrologClient.dispatch()``. Each maps to one
# (base_url, path, timeout) triple. Adding a third calculator means adding
# one row here — not a third ``calculate_*`` method.
FBT_ENGINE = "fbt"
DEPRECIATION_ENGINE = "depreciation"
DIV7A_ENGINE = "div7a"  # Phase D (mut-2026-08-24-mc20): Div7A_Engine gateway routing

# Per-asset Tier-1 classifier lookups in the depreciation engine dominate
# the audit-batch runtime; raise the read timeout to match the run_audit.py
# client's 900s default (app/clients/run_audit.py).
DEPRECIATION_AUDIT_TIMEOUT = httpx.Timeout(900.0, connect=15.0)


def prolog_url() -> str:
    """Return the upstream FBT-engine Prolog HTTP base URL.

    Resolution order:
        1. ``FBT_PROLOG_URL`` environment variable (set by docker-compose).
        2. Module default ``http://localhost:8081``.
    """
    return os.environ.get("FBT_PROLOG_URL", DEFAULT_PROLOG_URL).rstrip("/")


def depreciation_prolog_url() -> str:
    """Return the upstream Depreciation-engine Prolog HTTP base URL.

    Resolution order:
        1. ``DEPRECIATION_PROLOG_URL`` environment variable.
        2. Module default ``http://localhost:8082``.

    The per-engine env var pattern is Phase 3c.3.B option-α minimum-viable.
    Phase 3c.4 generalises to a single resolver.
    """
    return os.environ.get("DEPRECIATION_PROLOG_URL", DEFAULT_DEPRECIATION_URL).rstrip("/")


def div7a_engine_url() -> str:
    """Return the upstream Div7A_Engine base URL.

    Resolution order:
        1. ``DIV7A_ENGINE_URL`` environment variable.
        2. Module default ``http://localhost:8083``.

    Phase D (mut-2026-08-24-mc20): Div7A_Engine speaks native FastAPI at
    ``/v1/calculators/div7a/at/{period_uri}``; not the Prolog-shape endpoints
    of the FBT and depreciation engines. Uses the same dispatch abstraction
    as those engines for uniform transport-layer failure handling.
    """
    return os.environ.get("DIV7A_ENGINE_URL", DEFAULT_DIV7A_URL).rstrip("/")


class EngineAuthUnavailable(RuntimeError):
    """Raised when the gateway cannot mint an ID token for a Cloud Run
    audience that requires one.

    D22 fix (mut-2026-09-07-mc19 per Fable 2026-09-07 03:53 UTC verbatim):
    *"every engine call the gateway makes must attach an ID token whose
    audience is that engine's own URL, through one shared choke point,
    so no engine can ever be called untokenised again."*

    Prior mc14 shape: `_authenticated_headers` silently fell back to `{}`
    on any failure (import missing, metadata-fetch throw, empty netloc).
    Silent fallback means an engine locked down with allUsers-invoker-
    removed receives an unauth request → Cloud Run 403 → gateway maps to
    502 engine_auth_failed. Caller sees an opaque 502; operator has no
    signal that the gateway ITSELF is the broken side (vs the engine).

    New shape: for Cloud Run audiences, missing token IS a gateway-side
    fault raised at exactly the point-of-emission. `dispatch()` catches
    it + maps to a distinct 503 `engine_auth_local_fail` so it partitions
    cleanly from the engine-side 403 `engine_auth_failed`.

    Localhost / docker-compose / test audiences remain soft (return `{}`)
    because no ID token is applicable in those environments and dev-loop
    ergonomics require it.
    """

    def __init__(self, reason: str, audience: str, cause: Exception | None = None) -> None:
        super().__init__(
            f"gateway cannot mint ID token for Cloud Run audience "
            f"{audience!r}: {reason}"
        )
        self.reason = reason
        self.audience = audience
        self.cause = cause


def _is_localhost_audience(url: str) -> bool:
    """True iff ``url`` points at localhost (dev / docker-compose / test).

    Metadata-server ID-token fetch would fail (no metadata server on dev
    boxes) and add no security value (nothing to gate on the receiving
    side). Discriminator lives here so the two call sites in ``dispatch``
    stay symmetrical.

    Recognises: ``http://localhost``, ``http://127.``, ``http://0.0.0.0``,
    and the ``prolog:``/``depreciation:`` docker-compose service hostnames
    (which resolve inside the compose network only).
    """
    try:
        host = urlparse(url).hostname or ""
    except (ValueError, AttributeError):
        return True  # unparseable → err on side of no token
    if not host:
        return True  # empty/unparseable host → err on side of no token
    if host in ("localhost", "0.0.0.0"):
        return True
    if host.startswith("127."):
        return True
    # docker-compose service hostnames — resolve only inside the compose
    # network; no ID-token audience possible.
    if host in ("prolog", "depreciation", "div7a", "fbt-engine",
                "depreciation-engine", "div7a-engine"):
        return True
    # RFC 6761 special-use TLDs used by hermetic tests + local mocks:
    # .test / .example / .invalid / .localhost all reserved for non-production
    # use per IETF spec. Any hostname ending in one of these is safe to treat
    # as non-Cloud-Run for token purposes.
    for tld in (".test", ".example", ".invalid", ".localhost"):
        if host.endswith(tld):
            return True
    return False


def _authenticated_headers(url: str) -> dict[str, str]:
    """Return HTTP headers with a Cloud Run ID token for ``url``.

    D22 fix (mut-2026-09-07-mc19 per Fable 2026-09-07 03:53 UTC): for
    Cloud Run audiences, this function returns a Bearer header OR RAISES
    `EngineAuthUnavailable`. It NEVER silently returns `{}` for a Cloud
    Run audience — that was the mc14 defect surfaced when depreciation-
    engine locked down and the gateway kept calling it without a token.

    Localhost / docker-compose / test audiences remain soft (return `{}`)
    so dev + hermetic tests work without gcloud auth setup.

    Contract:
      - Cloud Run audience + `google-auth` importable + fetch succeeds
        → `{"Authorization": "Bearer <jwt>"}` with audience = scheme://netloc
      - Cloud Run audience + `google-auth` missing
        → raises `EngineAuthUnavailable(reason="google_auth_missing")`
      - Cloud Run audience + metadata fetch fails
        → raises `EngineAuthUnavailable(reason="metadata_fetch_failed", cause=exc)`
      - Cloud Run audience + unparseable scheme/netloc
        → raises `EngineAuthUnavailable(reason="invalid_audience_url")`
      - Localhost / docker-compose / test audience → `{}` (soft mode)

    Called per-request. `google-auth` internally caches tokens per audience
    until expiry, so hot-path overhead is a dict lookup; only the first
    call per audience per token-lifetime hits the metadata server.

    Escape hatch: set `CLAWDOG_ENGINE_AUTH_SOFT_MODE=1` in the environment
    to force soft-mode-return-{} on Cloud Run audiences too. Reserved for
    emergency rollback if a metadata-server outage would otherwise take
    the whole gateway down; NOT for normal operation. Emits a WARNING log
    on every use so its enablement is visible in Cloud Run logs.
    """
    if _is_localhost_audience(url):
        return {}

    # From here down, the audience is a Cloud Run URL (or equivalent).
    # ANY failure raises EngineAuthUnavailable; silent fallback to {} is
    # only reached via the emergency-escape env var below.

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        exc = EngineAuthUnavailable(
            reason="invalid_audience_url",
            audience=url,
        )
        _maybe_soft_mode_return(exc)
        raise exc
    audience = f"{parsed.scheme}://{parsed.netloc}"

    # D22 mc20 fix (per Fable 2026-09-07 04:19 UTC): try DIRECT metadata
    # call first (wire-authoritative Cloud Run identity endpoint); fall back
    # to google.oauth2.id_token.fetch_id_token second. Two independent paths
    # so a failure mode in one doesn't sink the other. Collect per-path
    # errors so the log names ALL attempts, not just the last.
    attempted: list[tuple[str, str]] = []  # [(path_name, error_repr), ...]

    # ---- Path 1: DIRECT metadata call (Fable's primary path) ----
    direct_token, direct_error = _fetch_id_token_direct_metadata(audience)
    if direct_token:
        return {"Authorization": f"Bearer {direct_token}"}
    if direct_error is not None:
        attempted.append(("direct_metadata", direct_error))

    # ---- Path 2: google.oauth2.id_token.fetch_id_token (fallback) ----
    if _GOOGLE_AUTH_AVAILABLE:
        try:
            request = _GoogleAuthRequest()
            token = _google_id_token.fetch_id_token(request, audience)
            if token:
                return {"Authorization": f"Bearer {token}"}
            attempted.append(("fetch_id_token", "returned_empty_token"))
        except Exception as exc:  # noqa: BLE001 — collected + re-raised below
            attempted.append((
                "fetch_id_token",
                f"{exc.__class__.__name__}: {exc}",
            ))
    else:
        attempted.append(("fetch_id_token", "google_auth_missing"))

    # ---- Both paths failed. Raise with full attempt-log. ----
    reason_summary = "; ".join(f"{path}={err}" for path, err in attempted)
    # D22 mc20 note-2 fix (per Fable 2026-09-07 04:41 UTC): emit as
    # structured JSON so Cloud Logging parses stderr into jsonPayload.
    # filterable fields (event, audience, attempts_list). Text-payload
    # logs land in Cloud Logging too but require substring filters; JSON
    # payload lets the SRE dashboard query on jsonPayload.event =
    # "engine_id_token_fetch_failed" directly.
    #
    # The message string is ALSO human-readable so grep-style tooling
    # still works; the JSON payload is emitted as `extra=` dict which
    # python's stdlib logger passes to formatters that support it. On
    # Cloud Run's default log handler, stderr writes that ARE valid JSON
    # are parsed as jsonPayload; anything else lands as textPayload.
    # See https://cloud.google.com/run/docs/logging#writing_structured_logs.
    structured_log = json.dumps({
        "severity": "ERROR",
        "event": "engine_id_token_fetch_failed",
        "audience": audience,
        "attempts": [{"path": p, "error": e} for p, e in attempted],
        "reason": f"all_mint_paths_failed: {reason_summary}",
        "remediation": (
            "(1) not running on Cloud Run (no metadata server); "
            "(2) Cloud Run metadata server outage; "
            "(3) audience URL rejected by IAM policy; "
            "(4) gateway runtime SA missing roles/run.invoker on target engine. "
            "gateway will surface as 503 engine_auth_local_fail."
        ),
    })
    # Emit twice: structured JSON to stderr (Cloud Logging picks up as
    # jsonPayload) + textPayload via logger.error (grep-friendly + also
    # lands in Cloud Logging). Both surfaces queryable.
    print(structured_log, file=sys.stderr, flush=True)
    logger.error(
        "engine_id_token_fetch_failed: audience=%s attempts=%s; "
        "ALL mint paths failed. Likely causes: (1) not running on Cloud Run "
        "(no metadata server); (2) Cloud Run metadata server outage; "
        "(3) audience URL rejected by IAM policy; (4) gateway runtime SA "
        "missing roles/run.invoker on the target engine. Raising "
        "EngineAuthUnavailable; dispatch() will surface as 503 "
        "engine_auth_local_fail (gateway-side identity failure, distinct "
        "from engine-side 403 engine_auth_failed).",
        audience, reason_summary,
    )
    auth_exc = EngineAuthUnavailable(
        reason=f"all_mint_paths_failed: {reason_summary}",
        audience=audience,
    )
    _maybe_soft_mode_return(auth_exc)
    raise auth_exc


def _fetch_id_token_direct_metadata(audience: str) -> tuple[str | None, str | None]:
    """Try Cloud Run's direct metadata identity endpoint.

    D22 mc20 primary mint path (per Fable 2026-09-07 04:19 UTC).
    Documented at
    https://cloud.google.com/run/docs/securing/service-identity#identity_tokens.

    Endpoint:
      GET http://metadata.google.internal/computeMetadata/v1/instance/
          service-accounts/default/identity?audience=<audience>
      Header: Metadata-Flavor: Google

    Returns (token, None) on success, (None, error_string) on failure.
    Tries `metadata.google.internal` first, falls back to `169.254.169.254`
    (the metadata server IP) in case DNS is not resolving.
    """
    last_err: str | None = None
    for host in _METADATA_HOSTS:
        url = f"http://{host}{_METADATA_ID_TOKEN_PATH}"
        params = {"audience": audience}
        try:
            with httpx.Client(timeout=_METADATA_TIMEOUT) as client:
                resp = client.get(url, params=params, headers=_METADATA_HEADER)
            if resp.status_code == 200:
                token = resp.text.strip()
                if token:
                    return token, None
                last_err = f"host={host} status=200 empty_body"
            else:
                # Cloud Run metadata returns 403 if the audience-with-audience
                # combination is rejected. 404 = wrong path. 401 = header missing.
                # Any non-200 is a hard fail for this host; move to next host or
                # fall through to fetch_id_token.
                body_preview = resp.text[:200] if resp.text else "<empty>"
                last_err = (
                    f"host={host} status={resp.status_code} body={body_preview!r}"
                )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            # Not on GCE / Cloud Run — metadata server unreachable.
            last_err = f"host={host} transport={exc.__class__.__name__}: {exc}"
            # Try next host in the loop.
            continue
        except Exception as exc:  # noqa: BLE001 — broad on purpose; direct-mint MUST NOT crash caller
            last_err = f"host={host} unexpected={exc.__class__.__name__}: {exc}"
            continue
    return None, last_err


def _maybe_soft_mode_return(exc: EngineAuthUnavailable) -> None:
    """If CLAWDOG_ENGINE_AUTH_SOFT_MODE=1, log + swallow the exception so
    caller falls through to unauthenticated request.

    Reserved for emergency rollback (metadata-server outage). Not for
    normal operation. If enabled, the WARNING log fires on every request
    so the abnormal state is visible.

    Return path: caller sees this function return normally + must then
    also check `_soft_mode_active_this_call` in a thread-local... too
    complex for a first cut. Simpler contract: this function LOGS the
    exception's details but does NOT swallow; caller-side handling of
    the raised exception is in `dispatch()` where the CLAWDOG_ENGINE_AUTH_
    SOFT_MODE branch converts the exception into a `{}` header dict +
    continues to the unauth request.

    Implementation kept in a helper so the escape-hatch semantics live
    in one place; see `PrologClient.dispatch()` for the caller-side
    check.
    """
    # No-op in this signature; the actual soft-mode swallowing happens
    # at dispatch() where the exception is caught. This helper exists
    # to make the escape-hatch contract discoverable in _authenticated_
    # headers' failure paths (all three raise sites call it before raise).
    return None


class PrologEngineUnavailable(RuntimeError):
    """Raised when the Prolog engine is unreachable or the HTTP transport fails.

    Covers four distinct underlying conditions:
      - ``httpx.ConnectError`` (engine URL not reachable, e.g. localhost
        fallback when env var is missing in production, or engine container
        is down)
      - ``httpx.TimeoutException`` (connect or read timeout exceeded)
      - ``httpx.HTTPStatusError`` (engine returned 4xx/5xx)
      - any other ``httpx.HTTPError`` subclass (transport-layer failure not
        captured by the three above)

    The route layer maps this to a structured FastAPI ``HTTPException`` with
    JSON body ``{error, error_code, detail}`` — NEVER a bare HTML 500.
    Closes Standing Rule #12 clause (e) violation. Banked under
    `mut-2026-05-28-mc06` after the OT #83 #1 wire-investigation surfaced
    the gap.
    """

    def __init__(
        self,
        error_code: str,
        detail: Any = None,
        *,
        engine: str | None = None,
        url: str | None = None,
    ) -> None:
        super().__init__(
            f"prolog engine unavailable: {error_code} (engine={engine!r}, url={url!r}, detail={detail!r})"
        )
        self.error_code = error_code
        self.detail = detail
        self.engine = engine
        self.url = url


class PrologCalculationError(RuntimeError):
    """Raised when the Prolog engine returns a structured error payload.

    Distinct from ``PrologEngineUnavailable`` — this fires when the engine
    REACHED us but signalled a computation failure via an ``error`` key in
    its JSON response body. The transport layer worked; the calculation did
    not.
    """

    def __init__(self, error: str, detail: Any = None) -> None:
        super().__init__(f"prolog calculation failed: {error} ({detail!r})")
        self.error = error
        self.detail = detail


class PrologClient:
    """Async HTTP client for the upstream Prolog calculator engines.

    Phase 3c.3.B onboards a SECOND engine surface (Depreciation) alongside
    the original FBT surface. The two engines run on separate ports with
    separate env vars.

    Phase 3c.4 Option-C PR α (`mut-2026-05-28-mc06`) introduces
    ``dispatch(engine, payload)`` as the single transport entry point.
    All four failure modes (ConnectError / TimeoutException / HTTPStatusError /
    other HTTPError) map to ``PrologEngineUnavailable``; structured Prolog-side
    errors continue to map to ``PrologCalculationError``. The two existing
    ``calculate_fbt()`` + ``depreciation_at()`` methods are retained as
    thin wrappers calling ``dispatch()`` so the existing test suite continues
    to pass without surface drift.

    Route-handler unification (collapsing the two FastAPI routes into one
    with discriminated-union body type) is DEFERRED to a future PR per
    Lesson #31 — the two routes have zero schema overlap today.
    """

    # Engine registry: maps engine id → (path, timeout) tuple. Base URL is
    # resolved per-call via ``_base_url_for(engine)`` so env-var changes are
    # picked up at request time, not init time.
    _ENGINE_REGISTRY: dict[str, dict[str, Any]] = {
        FBT_ENGINE: {
            "path": "/calculate_fbt",
            "timeout": DEFAULT_TIMEOUT,
        },
        # mc39-2026-08-29 rung 5 (Fable verdict amendment 2 §A2.8): the
        # depreciation-engine URN path migrated from the mc-designed batch-
        # audit stub `/api/v1/depreciation/audit` (never matched an engine)
        # to the F1-UPHELD-ratified single-asset point-in-time route
        # `/v1/calculators/depreciation/at/{period_uri}` (mc11-2026-08-02).
        # Templated path per Div7A pattern; dispatch() substitutes via
        # path_override at call site.
        DEPRECIATION_ENGINE: {
            "path_template": "/v1/calculators/depreciation/at/{period_uri}",
            "timeout": DEPRECIATION_AUDIT_TIMEOUT,
        },
        # Phase D (mut-2026-08-24-mc20): Div7A_Engine URN path is templated
        # with the period_uri; dispatch() substitutes at call time via a
        # per-engine path formatter. Timeout matches DEFAULT (30s connect 5s)
        # since Div7A calc is bounded arithmetic (§109E annuity formula), not
        # a batch classification like depreciation audit.
        DIV7A_ENGINE: {
            "path_template": "/v1/calculators/div7a/at/{period_uri}",
            "timeout": DEFAULT_TIMEOUT,
        },
    }

    def __init__(
        self,
        base_url: str | None = None,
        depreciation_base_url: str | None = None,
        div7a_base_url: str | None = None,
        timeout: httpx.Timeout | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (base_url or prolog_url()).rstrip("/")
        self._depreciation_base_url = (
            depreciation_base_url or depreciation_prolog_url()
        ).rstrip("/")
        self._div7a_base_url = (div7a_base_url or div7a_engine_url()).rstrip("/")
        self._timeout = timeout or DEFAULT_TIMEOUT
        self._client = client

    def _base_url_for(self, engine: str) -> str:
        """Resolve the engine's base URL. Per-engine env vars take precedence."""
        if engine == FBT_ENGINE:
            return self._base_url
        if engine == DEPRECIATION_ENGINE:
            return self._depreciation_base_url
        if engine == DIV7A_ENGINE:
            return self._div7a_base_url
        raise ValueError(f"unknown engine id: {engine!r}")

    async def dispatch(
        self,
        engine: str,
        payload: Mapping[str, Any],
        *,
        timeout_override: httpx.Timeout | None = None,
        path_override: str | None = None,
    ) -> dict[str, Any]:
        """Send ``payload`` to ``engine`` and return the parsed JSON response.

        Single transport entry point used by both calling routes. Catches all
        four httpx failure modes and maps them to ``PrologEngineUnavailable``
        with a discriminating ``error_code`` for the route layer to use when
        choosing the HTTP status code (502 for connect/HTTP failures, 503 for
        timeouts).

        Raises ``PrologEngineUnavailable`` on transport failure.
        Raises ``PrologCalculationError`` on structured engine-side error.
        Returns parsed JSON dict on success.
        """
        meta = self._ENGINE_REGISTRY.get(engine)
        if meta is None:
            raise ValueError(f"unknown engine id: {engine!r}")

        base_url = self._base_url_for(engine)
        # Phase D: templated engines (Div7A) supply path via path_override
        # at call site; classic engines (FBT + depreciation) use registry `path`.
        if path_override is not None:
            path = path_override
        elif "path" in meta:
            path = meta["path"]
        else:
            raise ValueError(
                f"engine {engine!r} has a `path_template` but no path_override supplied "
                f"to dispatch(); call site must template the URI itself"
            )
        url = f"{base_url}{path}"
        timeout = timeout_override or meta["timeout"]

        # Engine lock-down Step 1 (mut-2026-09-06-mc14) + D22 fix
        # (mut-2026-09-07-mc19 per Fable 2026-09-07 03:53 UTC):
        # attach Cloud Run ID token to every outbound engine call. For a
        # Cloud Run audience, `_authenticated_headers` returns the Bearer
        # header OR raises EngineAuthUnavailable — NEVER silently falls
        # back to {}. That fallback was the mc14 defect surfaced when
        # depreciation-engine locked down and the gateway kept calling it
        # tokenless (2026-09-07 03:53 UTC wire evidence). Dev/test/compose
        # audiences continue to receive {} (soft mode by construction).
        #
        # Emergency escape hatch: CLAWDOG_ENGINE_AUTH_SOFT_MODE=1 forces
        # the pre-mc19 silent-fallback behaviour. Reserved for metadata-
        # server outages that would otherwise take the whole gateway down;
        # emits a WARNING log so its enablement is visible.
        try:
            headers = _authenticated_headers(url)
        except EngineAuthUnavailable as auth_exc:
            if os.environ.get("CLAWDOG_ENGINE_AUTH_SOFT_MODE") == "1":
                logger.warning(
                    "engine_auth_soft_mode_engaged: audience=%s reason=%s; "
                    "CLAWDOG_ENGINE_AUTH_SOFT_MODE=1 in environment. "
                    "Sending unauthenticated request. Reserved for emergency "
                    "rollback ONLY; disable env var once metadata server is "
                    "restored.",
                    auth_exc.audience, auth_exc.reason,
                )
                headers = {}
            else:
                # Raise a distinct 503-mapped error so the caller can
                # partition gateway-side identity failure from engine-side
                # 403. `engine_auth_local_fail` is the discriminator.
                raise PrologEngineUnavailable(
                    error_code="engine_auth_local_fail",
                    detail={
                        "reason": auth_exc.reason,
                        "audience": auth_exc.audience,
                        "cause": (
                            f"{auth_exc.cause.__class__.__name__}: {auth_exc.cause}"
                            if auth_exc.cause is not None else None
                        ),
                    },
                    engine=engine,
                    url=url,
                ) from auth_exc

        try:
            if self._client is not None:
                resp = await self._client.post(
                    url, json=dict(payload), timeout=timeout, headers=headers
                )
            else:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, json=dict(payload), headers=headers)
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise PrologEngineUnavailable(
                error_code="engine_unreachable",
                detail=str(exc),
                engine=engine,
                url=url,
            ) from exc
        except httpx.TimeoutException as exc:
            raise PrologEngineUnavailable(
                error_code="engine_timeout",
                detail=str(exc),
                engine=engine,
                url=url,
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise PrologEngineUnavailable(
                error_code="engine_http_error",
                detail={
                    "status_code": exc.response.status_code,
                    "body": exc.response.text[:500],
                },
                engine=engine,
                url=url,
            ) from exc
        except httpx.HTTPError as exc:
            # Catch-all for any other httpx transport-layer failure
            # (RemoteProtocolError, NetworkError, etc.)
            raise PrologEngineUnavailable(
                error_code="engine_transport_error",
                detail=f"{exc.__class__.__name__}: {exc}",
                engine=engine,
                url=url,
            ) from exc

        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            # The Prolog engine signals computation failure via an `error` key
            # rather than HTTP status. Surface that as a structured exception.
            raise PrologCalculationError(
                data.get("error", "unknown"), data.get("detail")
            )
        return data

    async def calculate_fbt(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """POST to ``/calculate_fbt`` and return the parsed JSON response.

        Thin wrapper around ``dispatch(FBT_ENGINE, payload)`` retained for
        backward compatibility with existing tests. New code should call
        ``dispatch()`` directly. Raises ``PrologEngineUnavailable`` on
        transport failure (Phase 3c.4 PR α; previously raised raw
        ``httpx.HTTPStatusError``); raises ``PrologCalculationError`` on
        structured engine-side error.
        """
        return await self.dispatch(FBT_ENGINE, payload)

    async def depreciation_at(
        self, period_uri: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """POST to depreciation-engine ``/v1/calculators/depreciation/at/{period_uri}``.

        mc39-2026-08-29 rung 5 (Fable verdict amendment 2 §A2.8): the mc-
        designed batch-audit stub ``depreciation_audit()`` on
        ``/api/v1/depreciation/audit`` (never matched an engine) has been
        superseded by this single-asset point-in-time wrapper on the
        F1-UPHELD-ratified ``/v1/calculators/depreciation/at/{period_uri}``
        route. Path templating pattern mirrors ``div7a_at`` exactly.

        Gateway rider 2 (Fable §A2.4): the engine's `numeric_mode` field is
        pinned to `"serving"` server-side and never accepted from the caller.
        This wrapper enforces the pin by injecting the field into the
        forwarded payload; any caller-supplied `numeric_mode` is silently
        overwritten so `extra="forbid"` on the gateway `DepreciationAtInput`
        cannot be a workaround.
        """
        pinned_payload = {**dict(payload), "numeric_mode": "serving"}
        return await self.dispatch(
            DEPRECIATION_ENGINE,
            pinned_payload,
            path_override=f"/v1/calculators/depreciation/at/{period_uri.rsplit(':', 1)[-1]}",
        )

    async def depreciation_range(
        self, period_uri: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """POST to depreciation-engine
        ``/v1/calculators/depreciation/range/{period_uri}``.

        Fable D5 mc02 2026-09-04 sibling of `depreciation_at`. Same
        path-templating pattern; extracts the tail segment via
        `rsplit(':', 1)[-1]` which yields `"unscoped"` for the
        Fable-D5-ratified URN. The engine accepts any segment and
        ignores it (Fable D5: *"the engine is a primitive; the
        gateway composes"*); the tail extraction preserves the
        path-shape uniformity with /at/.

        Rider 2 (numeric_mode server-side pin) applied identically
        to /at/.
        """
        pinned_payload = {**dict(payload), "numeric_mode": "serving"}
        return await self.dispatch(
            DEPRECIATION_ENGINE,
            pinned_payload,
            path_override=f"/v1/calculators/depreciation/range/{period_uri.rsplit(':', 1)[-1]}",
        )

    async def div7a_at(
        self, period_uri: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """POST to Div7A_Engine ``/v1/calculators/div7a/at/{period_uri}``.

        Phase D (mut-2026-08-24-mc20): Div7A_Engine gateway routing. Unlike
        FBT + depreciation which POST to a fixed path, Div7A's canonical
        REST route templates the period_uri into the path per Div7A_Engine
        `api/main.py::calculate_at`. Uses the shared ``dispatch()``
        transport-failure machinery but with a per-call path override.
        """
        return await self.dispatch(
            DIV7A_ENGINE,
            payload,
            path_override=f"/v1/calculators/div7a/at/{period_uri}",
        )

    async def health(self) -> dict[str, Any]:
        """GET ``/health`` and return the parsed JSON response.

        Note: kept on the existing FBT-engine surface only; not generalised
        to engine-id dispatch because the FBT engine's /health is the only
        live health probe today. When the depreciation engine ships, this
        can grow into a ``health(engine)`` method symmetric with ``dispatch``.
        """
        url = f"{self._base_url}/health"
        if self._client is not None:
            resp = await self._client.get(url, timeout=self._timeout)
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


__all__ = [
    "DEFAULT_PROLOG_URL",
    "DEFAULT_DEPRECIATION_URL",
    "FBT_ENGINE",
    "DEPRECIATION_ENGINE",
    "DIV7A_ENGINE",
    "PrologClient",
    "PrologCalculationError",
    "PrologEngineUnavailable",
    "prolog_url",
    "depreciation_prolog_url",
]
