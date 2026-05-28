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

The existing ``calculate_fbt()`` + ``depreciation_audit()`` methods are kept
as thin wrappers calling ``dispatch()`` for backward compatibility with
existing tests. Route-handler unification (collapsing the two routes into a
single ``invoke_calculator`` with discriminated-union body type) is
DEFERRED to a future PR when a third calculator surfaces — per Lesson #31
the two routes have zero schema overlap today and forcing them into one
shape ahead of n=2 signal would be premature design.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx

DEFAULT_PROLOG_URL = "http://localhost:8081"
DEFAULT_DEPRECIATION_URL = "http://localhost:8082"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)

# Engine identifiers for ``PrologClient.dispatch()``. Each maps to one
# (base_url, path, timeout) triple. Adding a third calculator means adding
# one row here — not a third ``calculate_*`` method.
FBT_ENGINE = "fbt"
DEPRECIATION_ENGINE = "depreciation"

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
    ``calculate_fbt()`` + ``depreciation_audit()`` methods are retained as
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
        DEPRECIATION_ENGINE: {
            "path": "/api/v1/depreciation/audit",
            "timeout": DEPRECIATION_AUDIT_TIMEOUT,
        },
    }

    def __init__(
        self,
        base_url: str | None = None,
        depreciation_base_url: str | None = None,
        timeout: httpx.Timeout | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (base_url or prolog_url()).rstrip("/")
        self._depreciation_base_url = (
            depreciation_base_url or depreciation_prolog_url()
        ).rstrip("/")
        self._timeout = timeout or DEFAULT_TIMEOUT
        self._client = client

    def _base_url_for(self, engine: str) -> str:
        """Resolve the engine's base URL. Per-engine env vars take precedence."""
        if engine == FBT_ENGINE:
            return self._base_url
        if engine == DEPRECIATION_ENGINE:
            return self._depreciation_base_url
        raise ValueError(f"unknown engine id: {engine!r}")

    async def dispatch(
        self,
        engine: str,
        payload: Mapping[str, Any],
        *,
        timeout_override: httpx.Timeout | None = None,
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
        url = f"{base_url}{meta['path']}"
        timeout = timeout_override or meta["timeout"]

        try:
            if self._client is not None:
                resp = await self._client.post(
                    url, json=dict(payload), timeout=timeout
                )
            else:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, json=dict(payload))
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

    async def depreciation_audit(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """POST to ``/api/v1/depreciation/audit`` and return the parsed JSON.

        Thin wrapper around ``dispatch(DEPRECIATION_ENGINE, payload)`` retained
        for backward compatibility with existing tests. New code should call
        ``dispatch()`` directly. Raises ``PrologEngineUnavailable`` on
        transport failure (Phase 3c.4 PR α; previously raised raw
        ``httpx.HTTPStatusError``); raises ``PrologCalculationError`` on
        structured engine-side error.
        """
        return await self.dispatch(DEPRECIATION_ENGINE, payload)

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
    "PrologClient",
    "PrologCalculationError",
    "PrologEngineUnavailable",
    "prolog_url",
    "depreciation_prolog_url",
]
