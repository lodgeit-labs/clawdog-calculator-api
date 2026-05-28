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

from pathlib import Path
from typing import Annotated
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Path as PathParam

from api.lib.advisory_boundary import wrap_response
from api.lib.rate_table_resolver import (
    DEFAULT_TAXONOMY,
    RATIFIED_TAXONOMIES,
    rate_table_root_for,
)
from api.manifest_fidelity import build_manifest
from api.prolog_client import (
    PrologCalculationError,
    PrologClient,
    PrologEngineUnavailable,
)
from api.schemas.depreciation import DepreciationAuditInput
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
_DEPRECIATION_AUDIT_URI = "urn:sbrm:calculator:depreciation:audit"
_DEPRECIATION_FY2026 = "urn:sbrm:period:depreciation:fy2026"

_CALCULATOR_REGISTRY: dict[str, dict] = {
    _FBT_CAR_OC_URI: {
        "engine_method": "operating_cost",
        "engine_benefit_category": "car_operating_cost",
        "jurisdiction": "AU",
        "label": "FBT Car — Operating Cost Method",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTCarOperatingCostInput",
    },
    _DEPRECIATION_AUDIT_URI: {
        # Phase 3c.3.B onboarding (Andrew + Tracer ratified 2026-05-12 05:54 UTC).
        # Scope per Andrew: accounting-engine depreciation supports prime cost
        # + diminishing value only; /audit cross-checks ledger-side accumulated
        # depreciation against the accounting-method ideal. /resurrect and
        # /adjustment_journal are out of scope for β.2.B (separate registry
        # entries can be added later when those pipeline shapes are wired).
        "engine_method": "audit",
        "engine_benefit_category": "depreciation_audit",
        "jurisdiction": "AU",
        "label": "Depreciation — Audit (Prime Cost / Diminishing Value)",
        "supported_periods": [_DEPRECIATION_FY2026],
        "input_schema_ref": "#/components/schemas/DepreciationAuditInput",
    },
}


def _rate_table_root_for(period_uri: str, taxonomy: str = DEFAULT_TAXONOMY) -> Path:
    """Backward-compatible thin wrapper around the canonical resolver.

    The canonical implementation lives at
    ``api.lib.rate_table_resolver.rate_table_root_for`` since Phase 3c.2.c
    (mut-2026-05-12-mc16). This function is kept for in-route legibility and
    for the existing test_production_bundle.py import path; it delegates
    immediately. Per CLAWDOG/111 NN#2 the resolver path is now
    ``SBRM_RATE_TABLE/<calc>/<taxonomy>/<period_id>``.
    """
    return rate_table_root_for(period_uri, taxonomy)


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
    taxonomy: Annotated[
        str,
        Query(
            description=(
                "Bare-atom taxonomy axis value per CLAWDOG/111 §2. "
                "Ratified set: lodgeit_au_sbrm | hoffman_base. "
                "Default at Phase 3c.2: lodgeit_au_sbrm (only populated bundle). "
                "Strict-required discipline tightens at Phase 3c.3 when hoffman_base populates."
            ),
        ),
    ] = DEFAULT_TAXONOMY,
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

    if taxonomy not in RATIFIED_TAXONOMIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"taxonomy={taxonomy!r} is not in the ratified set "
                f"{sorted(RATIFIED_TAXONOMIES)} per CLAWDOG/111 §2."
            ),
        )

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
    except PrologEngineUnavailable as exc:
        # mc06-2026-05-28 Option-C PR α: catch transport-layer failures and
        # surface structured 502/503 rather than letting httpx.* propagate to
        # FastAPI's default bare-HTML 500 handler. Closes Standing Rule #12
        # clause (e) symmetrically across both calc routes (the depreciation
        # route has the live bare-500 today; this defends FBT in depth).
        status_code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if exc.error_code == "engine_timeout"
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": "engine_unavailable",
                "error_code": exc.error_code,
                "engine": exc.engine,
                "detail": exc.detail,
            },
        ) from exc
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
    rate_table_root = _rate_table_root_for(period_uri_decoded, taxonomy)
    try:
        manifest = build_manifest(rate_uris, rate_table_root)
    except (FileNotFoundError, OSError) as exc:
        # Defence in depth: if the bundled rate-table tree is missing or
        # unreadable, surface a structured 502 (Lesson #34 — surface, do
        # not paper over). The PRIMARY fix is the bundle shipped in the
        # Dockerfile + LODGEIT_FBT_REPO wired in cloud-run.yaml; this
        # branch exists so a future regression cannot revert to the bare
        # HTML 500 that obscured the Phase 3a deemed-dispatch root cause.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "manifest_rate_table_unavailable",
                "detail": (
                    f"failed to build manifest for {len(rate_uris)} rate URI(s) "
                    f"against root={rate_table_root!s}: {exc.__class__.__name__}: {exc}"
                ),
                "rate_uris": rate_uris,
                "rate_table_root": str(rate_table_root),
            },
        ) from exc

    response_payload = wrap_response(
        {
            "taxable_value": taxable_value,
            "trace": trace,
            "manifest": manifest,
        },
        jurisdiction=meta["jurisdiction"],
    )

    return CalculatorInvocationResponse.model_validate(response_payload)


# --- Phase 3c.3.B depreciation route (Option α minimum-viable) ---------------
#
# Andrew + Tracer ratified 2026-05-12 05:54 UTC. This is a sibling route to
# /v1/calculators/{calc_uri}/{period_uri}, deliberately kept SEPARATE from the
# FBT-shaped invoke route so that:
#   1. The FBT-shaped surface stays byte-untouched (a clean diff signal that
#      CLAWDOG/109 §8.3 abstraction-leak test is honoured at the route level).
#   2. The depreciation route can carry its native response shape
#      (audited_standard_assets list) without forcing the FBT route to evolve
#      into a polymorphic discriminated-union body.
#   3. Phase 3c.4 (the PrologClient + route generalisation sprint) has a
#      concrete second-implementation to study before designing the unified
#      shape — vs. doing the generalisation now from a one-data-point
#      extrapolation (Lesson #31 anti-pattern).
#
# When Phase 3c.4 unifies the surface, both routes converge under
# /v1/calculators/{calc_uri}/{period_uri} with discriminated dispatch.

_DEPRECIATION_RESPONSE_FIELDS = (
    "status",
    "transition_date",
    "method",
    "audited_standard_assets",
)


@router.post(
    "/calculators/depreciation/audit/{period_uri}",
    summary="Invoke the Depreciation Audit endpoint for the given URN-encoded period.",
    description=(
        "Phase 3c.3.B — onboards the upstream Depreciation Prolog engine's "
        "`/api/v1/depreciation/audit` endpoint through the REST surface. "
        "Cross-checks ledger-side `current_book_accum_dep` against the "
        "accounting-method projection (prime cost or diminishing value) at "
        "the supplied `transition_date`; surfaces a variance flag against "
        "the Brain-canon variance threshold "
        "(SBRM_RATE_TABLE/depreciation/<taxonomy>/<period>/audit-variance-threshold.md). "
        "Out of scope for β.2.B: `/resurrect` (asset register migration) and "
        "`/adjustment_journal` (Phase II pipeline) — each will land as a "
        "sibling route at the next depreciation onboarding rung."
    ),
)
async def invoke_depreciation_audit(
    period_uri: Annotated[str, PathParam(description="URL-encoded period URN.")],
    body: DepreciationAuditInput,
    prolog: Annotated[PrologClient, Depends(get_prolog_client)],
    taxonomy: Annotated[
        str,
        Query(
            description=(
                "Bare-atom taxonomy axis value per CLAWDOG/111 §2. "
                "Ratified set: lodgeit_au_sbrm | hoffman_base. "
                "At Phase 3c.3.B only lodgeit_au_sbrm is populated for "
                "depreciation; hoffman_base bundle authoring is deferred."
            ),
        ),
    ] = DEFAULT_TAXONOMY,
) -> dict:
    period_uri_decoded = unquote(period_uri)

    try:
        validate_period_uri(period_uri_decoded)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    if taxonomy not in RATIFIED_TAXONOMIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"taxonomy={taxonomy!r} is not in the ratified set "
                f"{sorted(RATIFIED_TAXONOMIES)} per CLAWDOG/111 §2."
            ),
        )

    meta = _CALCULATOR_REGISTRY.get(_DEPRECIATION_AUDIT_URI)
    if meta is None:  # pragma: no cover — registry is module-level constant
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="depreciation_audit calculator missing from registry",
        )
    if period_uri_decoded not in meta["supported_periods"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"period_uri={period_uri_decoded!r} is not supported by the "
                f"depreciation audit calculator. Supported: "
                f"{meta['supported_periods']}"
            ),
        )

    payload: dict = body.model_dump(by_alias=False, exclude_none=True)

    try:
        engine_response = await prolog.depreciation_audit(payload)
    except PrologEngineUnavailable as exc:
        # mc06-2026-05-28 Option-C PR α: catch transport-layer failures and
        # surface structured 502/503. This is the LIVE-FAILURE path closing
        # OT #83 #1 — production deploy has no DEPRECIATION_PROLOG_URL env
        # var, so depreciation_audit() falls through to localhost:8082 and
        # raises httpx.ConnectError which previously propagated as bare-HTML
        # 500 (Standing Rule #12 clause (e) violation; wire-verified mc03
        # 06:05 UTC + mc06 pre-flight 10:30 UTC).
        status_code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if exc.error_code == "engine_timeout"
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": "engine_unavailable",
                "error_code": exc.error_code,
                "engine": exc.engine,
                "detail": exc.detail,
            },
        ) from exc
    except PrologCalculationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": exc.error, "detail": exc.detail},
        ) from exc

    # Engine response shape: {status, transition_date, method, audited_standard_assets}.
    # Any missing primary field is a structural-defence-tier failure (Lesson #34
    # surface-do-not-paper-over).
    for required in _DEPRECIATION_RESPONSE_FIELDS:
        if required not in engine_response:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "error": "engine_response_missing_field",
                    "field": required,
                    "detail": engine_response,
                },
            )

    # Manifest fidelity: the depreciation engine consumes the variance
    # threshold rate from rates.pl. The Brain canon URI is fixed for the
    # period; we surface it in the manifest the same way FBT surfaces its
    # rate URIs. Future depreciation methods may consume more rate nodes;
    # the engine should populate `rate_uris_consumed` in its response so the
    # bridge does not need to know which rates a method touched. For now,
    # pin the audit-variance-threshold URI as the load-bearing manifest entry.
    rate_uris: list[str] = engine_response.get("rate_uris_consumed") or [
        f"urn:sbrm:rate:depreciation:{period_uri_decoded.split(':')[-1]}:audit-variance-threshold"
    ]
    rate_table_root = _rate_table_root_for(period_uri_decoded, taxonomy)
    try:
        manifest = build_manifest(rate_uris, rate_table_root)
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "manifest_rate_table_unavailable",
                "detail": (
                    f"failed to build manifest for {len(rate_uris)} rate URI(s) "
                    f"against root={rate_table_root!s}: {exc.__class__.__name__}: {exc}"
                ),
                "rate_uris": rate_uris,
                "rate_table_root": str(rate_table_root),
            },
        ) from exc

    response_payload = wrap_response(
        {
            "status": engine_response["status"],
            "transition_date": engine_response["transition_date"],
            "method": engine_response["method"],
            "audited_standard_assets": engine_response["audited_standard_assets"],
            "manifest": manifest,
        },
        jurisdiction=meta["jurisdiction"],
    )

    return response_payload


__all__ = ["router"]
