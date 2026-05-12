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
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx

DEFAULT_PROLOG_URL = "http://localhost:8081"
DEFAULT_DEPRECIATION_URL = "http://localhost:8082"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)

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


class PrologClient:
    """Async HTTP client for the upstream Prolog calculator engines.

    Phase 3c.3.B onboards a SECOND engine surface (Depreciation) alongside
    the original FBT surface. The two engines run on separate ports with
    separate env vars; the calc_uri → (engine_url, path) resolution lives in
    each ``calculate_*`` method below. Phase 3c.4 collapses this duplication
    into a single dispatcher.
    """

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

    async def calculate_fbt(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """POST to ``/calculate_fbt`` and return the parsed JSON response.

        Raises ``httpx.HTTPStatusError`` on 4xx/5xx; the route layer translates
        those into FastAPI ``HTTPException`` responses.
        """
        url = f"{self._base_url}/calculate_fbt"
        if self._client is not None:
            resp = await self._client.post(url, json=dict(payload), timeout=self._timeout)
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=dict(payload))
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            # The Prolog engine signals computation failure via an `error` key
            # rather than HTTP status. Surface that as a structured exception.
            raise PrologCalculationError(data.get("error", "unknown"), data.get("detail"))
        return data

    async def health(self) -> dict[str, Any]:
        """GET ``/health`` and return the parsed JSON response."""
        url = f"{self._base_url}/health"
        if self._client is not None:
            resp = await self._client.get(url, timeout=self._timeout)
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()

    async def depreciation_audit(
        self, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """POST to ``/api/v1/depreciation/audit`` and return the parsed JSON.

        Uses ``self._depreciation_base_url`` (separate env var from FBT) per
        Phase 3c.3.B option-α minimum-viable. Read timeout extended to 900s
        to match the upstream Tier-1 classifier batch runtime ceiling
        (run_audit.py reference).

        Raises ``httpx.HTTPStatusError`` on 4xx/5xx; the route layer translates
        those into FastAPI ``HTTPException`` responses.
        """
        url = f"{self._depreciation_base_url}/api/v1/depreciation/audit"
        timeout = DEPRECIATION_AUDIT_TIMEOUT
        if self._client is not None:
            resp = await self._client.post(
                url, json=dict(payload), timeout=timeout
            )
        else:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=dict(payload))
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            raise PrologCalculationError(
                data.get("error", "unknown"), data.get("detail")
            )
        return data


class PrologCalculationError(RuntimeError):
    """Raised when the Prolog engine returns a structured error payload."""

    def __init__(self, error: str, detail: Any = None) -> None:
        super().__init__(f"prolog calculation failed: {error} ({detail!r})")
        self.error = error
        self.detail = detail


__all__ = [
    "DEFAULT_PROLOG_URL",
    "PrologClient",
    "PrologCalculationError",
    "prolog_url",
]
