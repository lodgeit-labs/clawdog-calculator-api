"""``/v1/rates/...`` — rate-table discovery and inspection routes.

Implements:
    GET /v1/rates/{period_uri}             — list all rate-table fact-nodes for a period.
    GET /v1/rates/{period_uri}/{rate_id}   — return one rate-table node body + content_hash.

Per CLAWDOG/109 §7.3 the rate-table provenance surface is the moat: any
consumer can fetch the cited node and recompute the canonical hash. These
routes are the runtime surface that lets a consumer do that without scraping
the Brain repository directly.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import yaml
from fastapi import APIRouter, HTTPException, status

from api.manifest_fidelity import (
    declared_content_hash,
    hash_rate_table,
)
from api.schemas.invocation import validate_period_uri

router = APIRouter(prefix="/v1/rates", tags=["rates"])


def _rate_table_root_for(period_uri: str) -> Path:
    """Resolve the on-disk rate-table root for a given period URI.

    Mirrors ``api.routes.calculators._rate_table_root_for`` so both surfaces
    agree on lookup semantics.
    """
    override = os.environ.get("CLAWDOG_RATE_TABLE_ROOT")
    if override:
        return Path(override)
    fbt_repo = os.environ.get("LODGEIT_FBT_REPO", "/srv/lodgeit_fbt")
    parts = period_uri.split(":")
    calc, period_id = parts[3], parts[4]
    return Path(fbt_repo) / "SBRM_RATE_TABLE" / calc / period_id


def _split_frontmatter(content: str) -> dict[str, Any]:
    """Parse a rate-table fact-node's YAML frontmatter into a dict."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    body_lines: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        body_lines.append(line)
    return yaml.safe_load("\n".join(body_lines)) or {}


@router.get(
    "/{period_uri}",
    summary="List rate-table fact-nodes for a period (URN-encoded period URI).",
)
def list_rates(period_uri: str) -> dict[str, Any]:
    period_uri_decoded = unquote(period_uri)
    try:
        validate_period_uri(period_uri_decoded)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    root = _rate_table_root_for(period_uri_decoded)
    if not root.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"rate-table root not found for period_uri={period_uri_decoded!r}",
        )

    entries: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.md")):
        rate_id = path.stem
        live_hash = hash_rate_table(path)
        entries.append(
            {
                "rate_id": rate_id,
                "uri": _rate_uri_from_period(period_uri_decoded, rate_id),
                "content_hash": live_hash,
                "declared_hash": declared_content_hash(path),
                "hash_algorithm": "sha256",
                "drift": (declared_content_hash(path) is not None
                          and declared_content_hash(path) != live_hash),
            }
        )
    return {"period_uri": period_uri_decoded, "entries": entries}


@router.get(
    "/{period_uri}/{rate_id}",
    summary="Return a single rate-table fact-node body + content_hash.",
)
def get_rate(period_uri: str, rate_id: str) -> dict[str, Any]:
    period_uri_decoded = unquote(period_uri)
    try:
        validate_period_uri(period_uri_decoded)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    root = _rate_table_root_for(period_uri_decoded)
    path = root / f"{rate_id}.md"

    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"rate fact-node not found: {path}",
        )

    content = path.read_text(encoding="utf-8")
    fm = _split_frontmatter(content)
    live_hash = hash_rate_table(path)
    declared = declared_content_hash(path)

    return {
        "rate_id": rate_id,
        "uri": _rate_uri_from_period(period_uri_decoded, rate_id),
        "frontmatter": fm,
        "content_hash": live_hash,
        "declared_hash": declared,
        "hash_algorithm": "sha256",
        "drift": (declared is not None and declared != live_hash),
    }


def _rate_uri_from_period(period_uri: str, rate_id: str) -> str:
    """Project a rate URI from a period URI + rate_id slug.

    ``urn:sbrm:period:fbt:fy2026`` + ``statutory-fraction``
        → ``urn:sbrm:rate:fbt:fy2026:statutory-fraction``
    """
    parts = period_uri.split(":")
    calc, period_id = parts[3], parts[4]
    return f"urn:sbrm:rate:{calc}:{period_id}:{rate_id}"


__all__ = ["router"]
