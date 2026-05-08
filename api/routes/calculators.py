"""``/v1/calculators/...`` — calculator-invocation routes (Phase 3a Cut A).

Implements:
    POST /v1/calculators/{calc_uri}/{period_uri}   — calculator invocation
    GET  /v1/calculators                           — calculator discovery listing

Per CLAWDOG/109 §3.2 the REST surface is one of three coordinated egresses
over the same deterministic substrate. Phase 3a wires a single calculator
(FBT Car Operating Cost). Phase 3c is the test of whether the abstraction
holds under a second calculator.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Path as PathParam

from api.lib.advisory_boundary import wrap_response
from api.manifest_fidelity import build_manifest
from api.prolog_client import PrologCalculationError, PrologClient
from api.schemas.invocation import (
    CalculatorInvocationResponse,
    CalculatorListing,
    FBTCarOperatingCostInput,
    validate_calc_uri,
    validate_period_uri,
)

router = APIRouter(prefix="/v1", tags=["calculators"])


# --- Calculator registry (Phase 3a hardcoded; Phase 3c onboards a second) -----
#
# Map of calc_uri -> (engine_method, jurisdiction, label, period URIs, schema ref).
# The Phase 3a runway (CLAWDOG/109 §8.1) ships ONE entry. Phase 3c adds the
# second; if doing so requires changes here, the abstraction has leaked.

_FBT_CAR_OC_URI = "urn:sbrm:calculator:fbt:car-operating-cost"
_FBT_FY2026 = "urn:sbrm:period:fbt:fy2026"

_CALCULATOR_REGISTRY: dict[str, dict] = {
    _FBT_CAR_OC_URI: {
        "engine_method": "operating_cost",
        "engine_benefit_category": "car_operating_cost",
        "jurisdiction": "AU",
        "label": "FBT Car — Operating Cost Method",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTCarOperatingCostInput",
    },
}


def _rate_table_root_for(period_uri: str) -> Path:
    """Resolve the on-disk rate-table root for a given period URI.

    Resolution:
        1. If ``CLAWDOG_RATE_TABLE_ROOT`` is set, use it directly (test-fixture
           override; the test fixture vendors a pinned snapshot).
        2. Otherwise, resolve relative to ``$LODGEIT_FBT_REPO`` /
           ``SBRM_RATE_TABLE/fbt/<period_id>/`` for the FBT calculator.
    """
    override = os.environ.get("CLAWDOG_RATE_TABLE_ROOT")
    if override:
        return Path(override)

    fbt_repo = os.environ.get("LODGEIT_FBT_REPO", "/srv/lodgeit_fbt")
    # period_uri shape: urn:sbrm:period:<calc>:<period_id>
    parts = period_uri.split(":")
    calc, period_id = parts[3], parts[4]
    return Path(fbt_repo) / "SBRM_RATE_TABLE" / calc / period_id


async def get_prolog_client() -> PrologClient:
    """FastAPI dependency: yields a configured Prolog client."""
    return PrologClient()


@router.get(
    "/calculators",
    response_model=list[CalculatorListing],
    summary="List calculators available through the REST surface.",
)
async def list_calculators() -> list[CalculatorListing]:
    """Return a manifest of the calculators wired into this Phase 3a deployment.

    Phase 3a hardcodes one entry (FBT Car Operating Cost). Phase 3c onboards a
    second calculator; the registry above grows but the route signature does not.
    """
    out: list[CalculatorListing] = []
    for calc_uri, meta in _CALCULATOR_REGISTRY.items():
        out.append(
            CalculatorListing(
                calc_uri=calc_uri,
                label=meta["label"],
                method=meta["engine_method"],
                supported_periods=meta["supported_periods"],
                input_schema_ref=meta["input_schema_ref"],
                jurisdiction=meta["jurisdiction"],
            )
        )
    return out


@router.post(
    "/calculators/{calc_uri}/{period_uri}",
    response_model=CalculatorInvocationResponse,
    summary="Invoke a calculator for the given URN-encoded period.",
    description=(
        "Phase 3a Cut A — bare math + manifest + advisory. URL-encoded URN "
        "path params; the bridge re-validates them against the atom-vs-bridge "
        "boundary (CLAWDOG/110 §3.3) before forwarding to the Prolog engine. "
        "Response carries the calculator's native trace block, plus the "
        "manifest-fidelity block (live content_hashes per CLAWDOG/109 §7) and "
        "the advisory block (CLAWDOG/109 §6 / CLAWDOG/110 §3.2)."
    ),
)
async def invoke_calculator(
    calc_uri: Annotated[str, PathParam(description="URL-encoded calculator URN.")],
    period_uri: Annotated[str, PathParam(description="URL-encoded period URN.")],
    body: FBTCarOperatingCostInput,
    prolog: Annotated[PrologClient, Depends(get_prolog_client)],
) -> CalculatorInvocationResponse:
    calc_uri_decoded = unquote(calc_uri)
    period_uri_decoded = unquote(period_uri)

    try:
        validate_calc_uri(calc_uri_decoded)
        validate_period_uri(period_uri_decoded)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    meta = _CALCULATOR_REGISTRY.get(calc_uri_decoded)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"calc_uri={calc_uri_decoded!r} is not in the Phase 3a calculator "
                f"registry. Known: {sorted(_CALCULATOR_REGISTRY)}"
            ),
        )
    if period_uri_decoded not in meta["supported_periods"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"period_uri={period_uri_decoded!r} is not supported by calculator "
                f"{calc_uri_decoded!r}. Supported: {meta['supported_periods']}"
            ),
        )

    # The Prolog engine speaks snake_case OR camelCase on the wire; we normalise
    # to the engine's canonical snake_case shape via pydantic's `by_alias=False`.
    payload: dict = body.model_dump(by_alias=False, exclude_none=True)
    payload["benefit_category"] = meta["engine_benefit_category"]
    payload["method"] = meta["engine_method"]

    try:
        engine_response = await prolog.calculate_fbt(payload)
    except PrologCalculationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": exc.error, "detail": exc.detail},
        ) from exc

    taxable_value = engine_response.get("taxable_value")
    if taxable_value is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "engine_response_missing_taxable_value",
                "detail": engine_response,
            },
        )

    trace = engine_response.get("trace", {})
    rate_uris: list[str] = list(
        trace.get("applied_rate_table_uris")
        or engine_response.get("rate_uris_consumed", [])
        or []
    )
    rate_table_root = _rate_table_root_for(period_uri_decoded)
    manifest = build_manifest(rate_uris, rate_table_root)

    response_payload = wrap_response(
        {
            "taxable_value": taxable_value,
            "trace": trace,
            "manifest": manifest,
        },
        jurisdiction=meta["jurisdiction"],
    )

    return CalculatorInvocationResponse.model_validate(response_payload)


__all__ = ["router"]
