"""HTTP client for the upstream Prolog FBT_Engine.

Reaches the Prolog substrate (``LodgeiT_FBT/FBT_Engine.pl``) at
``$FBT_PROLOG_URL`` (default ``http://localhost:8081``) and returns the engine's
native ``DictOut`` shape unchanged. The bridge layer above (``api.routes``)
adds the manifest and advisory blocks; this client is bare transport.

Per CLAWDOG/109 §3.2, the direct-Prolog HTTP surface is the *truth-ground*.
This client treats it as such — no schema reshaping, no field renaming, no
silent fallbacks. The engine's response is opaque JSON in transit; the
calling route reads the fields it needs and surfaces the rest unchanged.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx

DEFAULT_PROLOG_URL = "http://localhost:8081"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


def prolog_url() -> str:
    """Return the upstream Prolog HTTP base URL.

    Resolution order:
        1. ``FBT_PROLOG_URL`` environment variable (set by docker-compose).
        2. Module default ``http://localhost:8081``.
    """
    return os.environ.get("FBT_PROLOG_URL", DEFAULT_PROLOG_URL).rstrip("/")


class PrologClient:
    """Async HTTP client for the FBT Prolog engine."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: httpx.Timeout | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (base_url or prolog_url()).rstrip("/")
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
