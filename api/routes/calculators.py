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
from typing import Annotated, Any
from urllib.parse import unquote

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi import Path as PathParam
from pydantic import ValidationError

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
    FBTBoardInput,
    FBTCarOperatingCostInput,
    FBTCarParkingActualInput,
    FBTCarParkingRegister12WkInput,
    FBTCarParkingStatutory228Input,
    FBTCarStatutoryFormulaInput,
    FBTDebtWaiverInput,
    FBTExpensePaymentInHouseInput,
    FBTExpensePaymentInput,
    FBTHousingInput,
    FBTLafhaInput,
    FBTLoanInput,
    FBTMealEntertainment5050Input,
    FBTMealEntertainmentRegister12WkInput,
    FBTPropertyInHouseInput,
    FBTPropertyInput,
    FBTResidualInHouseInput,
    FBTResidualInput,
    FBTTebeInput,
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

# --- Wave A URN constants (mut-2026-05-31-mc15) -----------------------------
# Phase 2a–2e original engine methods widened to the public REST + MCP surface.
# Each URN names the (jurisdiction-bare) calculator + method-atom per
# CLAWDOG/110 §3.3 atom-vs-bridge boundary. Jurisdiction lives on the registry
# entry below.
_FBT_LOAN_URI = "urn:sbrm:calculator:fbt:loan"
_FBT_DEBT_WAIVER_URI = "urn:sbrm:calculator:fbt:debt-waiver"
_FBT_EXPENSE_PAYMENT_URI = "urn:sbrm:calculator:fbt:expense-payment"
_FBT_EXPENSE_PAYMENT_IN_HOUSE_URI = "urn:sbrm:calculator:fbt:expense-payment-in-house"
_FBT_PROPERTY_URI = "urn:sbrm:calculator:fbt:property"
_FBT_PROPERTY_IN_HOUSE_URI = "urn:sbrm:calculator:fbt:property-in-house"
_FBT_RESIDUAL_URI = "urn:sbrm:calculator:fbt:residual"
_FBT_RESIDUAL_IN_HOUSE_URI = "urn:sbrm:calculator:fbt:residual-in-house"

# --- Wave B URN constants (mut-2026-05-31-mc17) -----------------------------
# Phase 2f–2i single-method calculators widened to the public REST + MCP surface.
_FBT_HOUSING_URI = "urn:sbrm:calculator:fbt:housing"
_FBT_LAFHA_URI = "urn:sbrm:calculator:fbt:lafha"
_FBT_BOARD_URI = "urn:sbrm:calculator:fbt:board"
_FBT_TEBE_URI = "urn:sbrm:calculator:fbt:tebe"

# --- Wave C URN constants (mut-2026-05-31-mc19) -----------------------------
# Phase 2j-2k method-dispatching calculators + Car-SF (legacy v1) widened
# per CLAWDOG/110 §3.3 atom-vs-bridge γ-1 option (URN names the method).
_FBT_CAR_PARKING_ACTUAL_URI = "urn:sbrm:calculator:fbt:car-parking-actual"
_FBT_CAR_PARKING_STATUTORY_228_URI = "urn:sbrm:calculator:fbt:car-parking-statutory-228"
_FBT_CAR_PARKING_REGISTER_12WK_URI = "urn:sbrm:calculator:fbt:car-parking-register-12wk"
_FBT_MEAL_ENTERTAINMENT_50_50_URI = "urn:sbrm:calculator:fbt:meal-entertainment-50-50"
_FBT_MEAL_ENTERTAINMENT_REGISTER_12WK_URI = "urn:sbrm:calculator:fbt:meal-entertainment-register-12wk"
_FBT_CAR_STATUTORY_FORMULA_URI = "urn:sbrm:calculator:fbt:car-statutory-formula"

_CALCULATOR_REGISTRY: dict[str, dict] = {
    _FBT_CAR_OC_URI: {
        "engine_method": "operating_cost",
        "engine_benefit_category": "car_operating_cost",
        "jurisdiction": "AU",
        "label": "FBT Car — Operating Cost Method",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTCarOperatingCostInput",
    },
    # --- Wave A Phase 2a–2e public-API widening (mut-2026-05-31-mc15) -----
    # Each entry wraps an existing LodgeiT_FBT predicate; engine method-atom
    # matches the `route_calc/4` table at FBT_Engine.pl L699–L772 (LodgeiT_FBT
    # `81e1a0ff`); benefit-category matches the engine's `benefit_category`
    # field shape. Zero rate-table consumption for std variants; in-house
    # variants consume FY2026 `in-house-benefit-cap` per Standing Rule #6.
    _FBT_LOAN_URI: {
        "engine_method": "loan_benefit_type_2",
        "engine_benefit_category": "loan",
        "jurisdiction": "AU",
        "label": "FBT Loan — Type 2 (FBTAA Division 4 ss.16–19)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTLoanInput",
    },
    _FBT_DEBT_WAIVER_URI: {
        "engine_method": "debt_waiver",
        "engine_benefit_category": "debt_waiver",
        "jurisdiction": "AU",
        "label": "FBT Debt Waiver (FBTAA s.16; Type 2 only)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTDebtWaiverInput",
    },
    _FBT_EXPENSE_PAYMENT_URI: {
        "engine_method": "expense_payment",
        "engine_benefit_category": "expense_payment",
        "jurisdiction": "AU",
        "label": "FBT Expense Payment — std (FBTAA Division 5 ss.20–24)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTExpensePaymentInput",
    },
    _FBT_EXPENSE_PAYMENT_IN_HOUSE_URI: {
        "engine_method": "in_house_expense_payment",
        "engine_benefit_category": "expense_payment_in_house",
        "jurisdiction": "AU",
        "label": "FBT Expense Payment — In-House (FBTAA s.62 cap)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTExpensePaymentInHouseInput",
    },
    _FBT_PROPERTY_URI: {
        "engine_method": "property",
        "engine_benefit_category": "property",
        "jurisdiction": "AU",
        "label": "FBT Property — std (FBTAA Division 7 ss.40–44)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTPropertyInput",
    },
    _FBT_PROPERTY_IN_HOUSE_URI: {
        "engine_method": "in_house_property",
        "engine_benefit_category": "property_in_house",
        "jurisdiction": "AU",
        "label": "FBT Property — In-House (FBTAA s.62 cap)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTPropertyInHouseInput",
    },
    _FBT_RESIDUAL_URI: {
        "engine_method": "residual",
        "engine_benefit_category": "residual",
        "jurisdiction": "AU",
        "label": "FBT Residual — std (FBTAA Division 12 ss.45–52)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTResidualInput",
    },
    _FBT_RESIDUAL_IN_HOUSE_URI: {
        "engine_method": "in_house_residual",
        "engine_benefit_category": "residual_in_house",
        "jurisdiction": "AU",
        "label": "FBT Residual — In-House (FBTAA s.62 cap)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTResidualInHouseInput",
    },
    # End Wave A registry entries.
    # --- Wave B Phase 2f–2i public-API widening (mut-2026-05-31-mc17) -----
    # 4 single-method calculators. Engine method-atoms match the `route_calc/4`
    # table at FBT_Engine.pl L692–L772 (LodgeiT_FBT `81e1a0ff`). Sheet-parity
    # carry-overs:
    # - Board: OT #94 row 35 Waqas WAIT-STATE (predicate is statute-faithful)
    # - Housing: clean ship
    # - LAFHA: clean ship; caller supplies pre-computed exempt_food_component
    # - TEBE: clean ship; 50/50-split is sheet/UI-layer concern
    _FBT_HOUSING_URI: {
        "engine_method": "housing_non_remote",
        "engine_benefit_category": "housing",
        "jurisdiction": "AU",
        "label": "FBT Housing — Non-Remote (FBTAA s.26)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTHousingInput",
    },
    _FBT_LAFHA_URI: {
        "engine_method": "lafha_std",
        "engine_benefit_category": "lafha",
        "jurisdiction": "AU",
        "label": "FBT LAFHA — Living-Away-From-Home Allowance (FBTAA s.31; Type 2 only)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTLafhaInput",
    },
    _FBT_BOARD_URI: {
        "engine_method": "board_std",
        "engine_benefit_category": "board",
        "jurisdiction": "AU",
        "label": "FBT Board (FBTAA s.36; sheet row 35 sheet-vs-statute divergence parked under OT #94)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTBoardInput",
    },
    _FBT_TEBE_URI: {
        "engine_method": "tebe_std",
        "engine_benefit_category": "tebe",
        "jurisdiction": "AU",
        "label": "FBT TEBE — Tax-Exempt Body Entertainment (FBTAA s.39)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTTebeInput",
    },
    # End Wave B registry entries.
    # --- Wave C Phase 2j–2k + Car-SF public-API widening (mut-2026-05-31-mc19) -----
    # 6 method-atoms across 3 calc URN-classes. Per CLAWDOG/110 §3.3 atom-vs-bridge
    # γ-1 option (Brain PR #303 sprint design): the URN names the method
    # explicitly rather than smuggling it in the body. Engine method-atoms match
    # the `route_calc/4` table at FBT_Engine.pl L692–L772 (LodgeiT_FBT `81e1a0ff`).
    # Sheet-parity carry-overs:
    # - Car Parking WRT T1: OT #96 row 63 Waqas WAIT-STATE
    # - Car Parking ACT/SFT/WRT-T2 + Meal Entertainment Actual/12-Wk T1/T2
    #   + Car-SF: clean ships
    _FBT_CAR_PARKING_ACTUAL_URI: {
        "engine_method": "actual",
        "engine_benefit_category": "car_parking",
        "jurisdiction": "AU",
        "label": "FBT Car Parking — Actual Method (FBTAA Division 10A; simple-sum)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTCarParkingActualInput",
    },
    _FBT_CAR_PARKING_STATUTORY_228_URI: {
        "engine_method": "statutory_228",
        "engine_benefit_category": "car_parking",
        "jurisdiction": "AU",
        "label": "FBT Car Parking — 228-Day Statutory Formula (FBTAA s.39FA)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTCarParkingStatutory228Input",
    },
    _FBT_CAR_PARKING_REGISTER_12WK_URI: {
        "engine_method": "register_12wk",
        "engine_benefit_category": "car_parking",
        "jurisdiction": "AU",
        "label": "FBT Car Parking — 12-Week Register (FBTAA s.39GB; WRT T1 sheet row 63 sheet-vs-statute divergence parked under OT #96)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTCarParkingRegister12WkInput",
    },
    _FBT_MEAL_ENTERTAINMENT_50_50_URI: {
        "engine_method": "50_50",
        "engine_benefit_category": "meal_entertainment",
        "jurisdiction": "AU",
        "label": "FBT Meal Entertainment — 50/50 Split (FBTAA s.37CA; Division 9A)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTMealEntertainment5050Input",
    },
    _FBT_MEAL_ENTERTAINMENT_REGISTER_12WK_URI: {
        "engine_method": "register_12wk",
        "engine_benefit_category": "meal_entertainment",
        "jurisdiction": "AU",
        "label": "FBT Meal Entertainment — 12-Week Register (FBTAA s.37CB; Division 9A)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTMealEntertainmentRegister12WkInput",
    },
    _FBT_CAR_STATUTORY_FORMULA_URI: {
        "engine_method": "car_statutory_formula",
        "engine_benefit_category": "car_statutory_formula",
        "jurisdiction": "AU",
        "label": "FBT Car — Statutory Formula (FBTAA s.9; rate-table-fed; consumes statutory-fraction + days-in-year)",
        "supported_periods": [_FBT_FY2026],
        "input_schema_ref": "#/components/schemas/FBTCarStatutoryFormulaInput",
    },
    # End Wave C registry entries; the existing depreciation entry follows.
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


# --- Per-URN input-model dispatch table (mut-2026-05-31-mc15) ---------------
# Wave A widens the existing single-URN body type to a per-URN dispatch. The
# generic ``/v1/calculators/{calc_uri}/{period_uri}`` route now accepts a raw
# JSON body + validates against the URN's registered pydantic input class.
# Per Lesson #31 anti-premature-design: this dict IS the framework; growing
# it for each new calculator is the load-bearing application, not a separate
# abstraction.
#
# Source of truth for which calc-URIs have a pydantic input schema. The MCP
# tool registry at ``api/services/mcp_tool_registry.py`` mirrors this dict
# for the JSON-RPC tools/list surface; both must agree. See
# ``tests/test_input_model_registry_parity.py`` for the binary-failure gate
# that enforces equality (mut-2026-05-31-mc15 production-bundle assertion #1
# extension).
_CALC_INPUT_MODEL_REST: dict[str, type] = {
    _FBT_CAR_OC_URI: FBTCarOperatingCostInput,
    # Wave A (mut-2026-05-31-mc15)
    _FBT_LOAN_URI: FBTLoanInput,
    _FBT_DEBT_WAIVER_URI: FBTDebtWaiverInput,
    _FBT_EXPENSE_PAYMENT_URI: FBTExpensePaymentInput,
    _FBT_EXPENSE_PAYMENT_IN_HOUSE_URI: FBTExpensePaymentInHouseInput,
    _FBT_PROPERTY_URI: FBTPropertyInput,
    _FBT_PROPERTY_IN_HOUSE_URI: FBTPropertyInHouseInput,
    _FBT_RESIDUAL_URI: FBTResidualInput,
    _FBT_RESIDUAL_IN_HOUSE_URI: FBTResidualInHouseInput,
    # Wave B (mut-2026-05-31-mc17)
    _FBT_HOUSING_URI: FBTHousingInput,
    _FBT_LAFHA_URI: FBTLafhaInput,
    _FBT_BOARD_URI: FBTBoardInput,
    _FBT_TEBE_URI: FBTTebeInput,
    # Wave C (mut-2026-05-31-mc19)
    _FBT_CAR_PARKING_ACTUAL_URI: FBTCarParkingActualInput,
    _FBT_CAR_PARKING_STATUTORY_228_URI: FBTCarParkingStatutory228Input,
    _FBT_CAR_PARKING_REGISTER_12WK_URI: FBTCarParkingRegister12WkInput,
    _FBT_MEAL_ENTERTAINMENT_50_50_URI: FBTMealEntertainment5050Input,
    _FBT_MEAL_ENTERTAINMENT_REGISTER_12WK_URI: FBTMealEntertainmentRegister12WkInput,
    _FBT_CAR_STATUTORY_FORMULA_URI: FBTCarStatutoryFormulaInput,
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
    body: Annotated[
        FBTCarOperatingCostInput
        | FBTLoanInput
        | FBTDebtWaiverInput
        | FBTExpensePaymentInput
        | FBTExpensePaymentInHouseInput
        | FBTPropertyInput
        | FBTPropertyInHouseInput
        | FBTResidualInput
        | FBTResidualInHouseInput
        | FBTHousingInput
        | FBTLafhaInput
        | FBTBoardInput
        | FBTTebeInput
        | FBTCarParkingActualInput
        | FBTCarParkingStatutory228Input
        | FBTCarParkingRegister12WkInput
        | FBTMealEntertainment5050Input
        | FBTMealEntertainmentRegister12WkInput
        | FBTCarStatutoryFormulaInput
        | dict,
        Body(
            description=(
                "Calculator input body. The schema dispatched per `calc_uri` "
                "path param; see the `_CALC_INPUT_MODEL_REST` registry in "
                "`api/routes/calculators.py` for the per-URN pydantic class "
                "binding. FastAPI presents all wrapped input types as a "
                "Union; the route validates the body against the URN's "
                "specific class at request time and surfaces a structured "
                "422 on mismatch."
            ),
        ),
    ],
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

    # Per-URN input validation via the dispatch table (mut-2026-05-31-mc15).
    # FastAPI parses the body as a Union of all wrapped input types (or as a
    # dict when none match strictly), so the OpenAPI schema documents every
    # possible per-URN shape. At runtime we look up the URN's specific pydantic
    # class and validate AGAINST IT (independent of Union-discrimination) so a
    # request body matching multiple input shapes is unambiguous — the
    # calc_uri is the discriminator, not duck-typing.
    input_model = _CALC_INPUT_MODEL_REST.get(calc_uri_decoded)
    if input_model is None:  # pragma: no cover — registry invariant
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"calc_uri={calc_uri_decoded!r} is in the calculator registry "
                f"but missing from _CALC_INPUT_MODEL_REST. Schema dispatch "
                f"will not work; please add the entry."
            ),
        )
    # Normalise body to dict regardless of whether FastAPI parsed it as a
    # pydantic instance or a raw dict (Union dispatch is opportunistic).
    if hasattr(body, "model_dump"):
        raw_body = body.model_dump(by_alias=True, exclude_none=True)
    else:
        raw_body = dict(body)
    try:
        validated_body = input_model(**raw_body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    # The Prolog engine speaks snake_case OR camelCase on the wire; we normalise
    # to the engine's canonical snake_case shape via pydantic's `by_alias=False`.
    payload: dict = validated_body.model_dump(by_alias=False, exclude_none=True)
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

    # --- Phase 3a (mut-2026-06-19-mc07-ot-104-calc-api-fbttype-gross-up-output)
    # OT #104 sprint PR β: surface engine's gross-up + RFBA notional fields
    # at calc-api response. Engine PR α (LodgeiT_FBT PR #44) added:
    #   * fbt_type / gross_up_factor / grossed_up_taxable_value / fbt_payable
    #     on Phase 2l SF + Phase 2l OC.
    #   * rfba_notional_taxable_value / rfba_notional_grossed_up_t2 already
    #     emitted since Rung 3 mut-2026-05-21-mc06 but dropped here.
    # We pass them through ONLY when the engine emits them (calculators that
    # do not emit gross-up keep the pre-mc07 wire shape byte-stable).
    gross_up_passthrough: dict[str, Any] = {}
    for key in (
        "fbt_type",
        "gross_up_factor",
        "grossed_up_taxable_value",
        "fbt_payable",
        "rfba_notional_taxable_value",
        "rfba_notional_grossed_up_t2",
    ):
        if key in engine_response and engine_response[key] is not None:
            gross_up_passthrough[key] = engine_response[key]

    response_payload = wrap_response(
        {
            "taxable_value": taxable_value,
            "trace": trace,
            "manifest": manifest,
            **gross_up_passthrough,
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
