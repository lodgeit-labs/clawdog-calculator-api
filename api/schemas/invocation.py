"""Calculator-invocation pydantic schemas.

Implements CLAWDOG/110 §3.3 Non-Negotiable #3 (Atom-vs-Bridge Boundary):
calculator-invocation atoms carry **identity only**; interpretation lives at
the bridge. The schemas below validate that period URIs, calculator URIs, and
rate-table URIs do not smuggle interpretation (jurisdiction, currency, etc.)
into atom fields. Smuggling patterns fail validation with a structured error
(Lesson #36 anchor).

Phase 3a scope:
    POST /v1/calculators/{calc_uri}/{period_uri}
        Body: FBTCarOperatingCostInput  (the only calculator wired through the
        bridge in this phase; CLAWDOG/109 §8.1).
    Response: CalculatorInvocationResponse with manifest + advisory + trace.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- URI shape validators (atom-vs-bridge boundary) ---------------------------
#
# Period URI:    urn:sbrm:period:<calc>:<period_id>
# Calculator URI: urn:sbrm:calculator:<calc>:<method>  OR
#                 urn:lodgeit:calculator:<calc>
# Rate URI:      urn:sbrm:rate:<calc>:<period_id>:<rate_id>
#
# Forbidden smuggling shapes: a period_id or calc field that bakes in a
# jurisdiction (e.g. "AU_FY26"), a "year_with_juris" field, etc. Jurisdiction
# is a SEPARATE first-class parameter; period is naked.

_PERIOD_URI_RE = re.compile(r"^urn:sbrm:period:[a-z0-9_-]+:[a-z0-9_-]+$")
_CALC_URI_RE = re.compile(
    r"^urn:(?:sbrm|lodgeit):calculator:[a-z0-9_-]+(?::[a-z0-9_-]+)?$"
)
_RATE_URI_RE = re.compile(
    r"^urn:sbrm:rate:[a-z0-9_-]+:[a-z0-9_-]+:[a-z0-9_-]+$"
)
# Smuggling sentinels — patterns that fuse jurisdiction or currency into an atom.
_SMUGGLING_SENTINELS = (
    re.compile(r"_au_", re.IGNORECASE),
    re.compile(r"_uk_", re.IGNORECASE),
    re.compile(r"_aud_", re.IGNORECASE),
    re.compile(r"_gbp_", re.IGNORECASE),
)


def _reject_smuggling(value: str, field_name: str) -> str:
    for pat in _SMUGGLING_SENTINELS:
        if pat.search(value):
            raise ValueError(
                f"{field_name}={value!r} appears to smuggle jurisdiction/currency "
                f"interpretation into an atom (matched {pat.pattern!r}). Pass "
                f"jurisdiction as a separate parameter; keep atoms bare. "
                f"(CLAWDOG/110 §3.3 Non-Negotiable #3 / Lesson #36)"
            )
    return value


class FBTCarOperatingCostInput(BaseModel):
    """Input for the FBT Car Operating Cost method (Phase 3a Cut A).

    Field naming mirrors the upstream Prolog engine's request shape (snake_case
    via FastAPI's alias mapping, accepting both snake_case and the camelCase
    used by the existing fbt_tester.py compatibility surface).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    business_use_percentage: float = Field(
        ..., ge=0, le=100, alias="businessUsePercentage",
        description="Business-use % of total operating costs. Clamped to [0, 100] by the engine.",
    )
    employee_contribution: float = Field(
        0, ge=0, alias="employeeContribution",
        description="Post-tax employee contribution toward the benefit (AUD).",
    )
    form_of_finance: str = Field(
        ..., alias="formOfFinance",
        description="One of: owned | hire_purchase | leased | unspecified.",
    )
    lease_payments: float | None = Field(
        None, ge=0, alias="leasePayments",
        description="Lease payments for the period (AUD); null/absent if not leased.",
    )
    fuel_repairs_servicing: float | None = Field(
        None, ge=0, alias="fuelRepairsServicing",
        description="Fuel + repairs + servicing for the period (AUD).",
    )
    registration_insurance: float | None = Field(
        None, ge=0, alias="registrationInsurance",
        description="Registration + insurance for the period (AUD).",
    )
    no_private_use_reduction: float | None = Field(
        None, ge=0, alias="noPrivateUseReduction",
        description="No-private-use reduction (AUD).",
    )
    # Optional deemed-amounts dispatch fields (fire when all three present and
    # form_of_finance is owned | hire_purchase per FBT_Engine.pl
    # fbt_oc_deemed_dispatch).
    acquisition_date: str | None = Field(
        None, alias="acquisitionDate",
        description="ISO date string (e.g. 2024-04-01); drives deemed-depreciation tier dispatch.",
    )
    opening_depreciated_value: float | None = Field(
        None, ge=0, alias="openingDepreciatedValue",
        description="Opening depreciated value at start of FBT year (AUD). "
        "Mutually exclusive with acquisition_cost per engine Lesson #14 "
        "strict-validation (OT #81 Rung 2 mc07).",
    )
    # OT #81 Rung 2 (mut-2026-05-22-mc07) chained-DV entry-point: acquisition_cost
    # is the original acquisition cost AUD that the engine uses as the chained-
    # DV entry-point depreciated value. When supplied with acquisition_date (and
    # WITHOUT opening_depreciated_value), the engine dispatches to the chained-DV
    # walk predicate (fbt_car_oc_deemed_amounts_chained/9 added in OT #81 Rung 3
    # mc08) which walks each FBT year from acquisition forward, applying the
    # statutory per-year depreciation primitive once per year. This reproduces
    # the NTAA toolkit's chained-DV reference data byte-exactly (closed by
    # LodgeiT_FBT PR #26 + Brain canon node CALCULATORS/FBT/140 content_hash
    # 552e53cf3b7de5bd7c140deef6c3328afbb98d9d9637fb65f36feabca20a3fea).
    # Strict mutual-exclusion vs opening_depreciated_value is enforced engine-side
    # in validate_chained_dv_inputs/2 per Lesson #14; surfaces as a Prolog throw
    # bubbled to FastAPI as a structured error.
    acquisition_cost: float | None = Field(
        None, ge=0, alias="acquisitionCost",
        description="Original acquisition cost (AUD) for the chained-DV walk; "
        "chained-DV entry-point. Mutually exclusive with opening_depreciated_value. "
        "When supplied with acquisition_date (and without opening_depreciated_value), "
        "the engine dispatches to the OT #81 chained-DV walk predicate (mc08).",
    )
    days_held_in_fbt_year: int | None = Field(
        None, ge=0, le=366, alias="daysHeldInFBTYear",
        description="Days the car was held during the FBT year [0..366]. "
        "Required for in-FY-acquisition chained-DV cases (acquisition_date "
        "within the FBT year) where the engine's default of 365 would over-"
        "state the partial-year leg. Multi-FY chains do NOT need this field "
        "(their FY2026 leg is always a full year).",
    )
    # Legacy/override path — retained for parity with the engine's optional
    # explicit deemed_total override; not used in PR-D Case 5.
    deemed_total: float | None = Field(
        None, ge=0, alias="deemedTotal",
        description="Optional explicit deemed_total (AUD) override.",
    )

    @field_validator("form_of_finance")
    @classmethod
    def _validate_form_of_finance(cls, v: str) -> str:
        allowed = {"owned", "hire_purchase", "leased", "unspecified", "other"}
        v_lower = (v or "").strip().lower()
        if v_lower not in allowed:
            raise ValueError(
                f"form_of_finance={v!r} is not one of {sorted(allowed)}. "
                f"Bridge does not interpret unknown values."
            )
        return v_lower

    @field_validator("acquisition_date")
    @classmethod
    def _validate_acquisition_date(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError(
                f"acquisition_date={v!r} must be ISO yyyy-mm-dd; date arithmetic "
                f"is bridge-side interpretation, the atom is naked."
            )
        return v


# =============================================================================
# Wave A — Phase 2a–2e public-API widening (mut-2026-05-31-mc15)
# =============================================================================
#
# 8 method-atom input schemas wrapping the existing Phase 2a–2e Prolog
# predicates in LodgeiT_FBT (engine reference: FBT_Engine.pl). Each schema
# mirrors the engine's `calculate_fbt_<method>/2` input contract documented
# in the predicate's comment block. The bridge sends snake_case to the
# engine; pydantic accepts both snake_case and the camelCase from
# fbt_tester.py / the original FY2026 sheet inputs (via `alias`).
#
# Per Standing Rule #6 (Hoffman temporal-dimension): none of the Wave A
# calculators consume rate-tables at the engine layer (zero `rate_uris_consumed`
# in their respective predicate outputs as of LodgeiT_FBT `81e1a0ff`), so
# Standing Rule #12's production-bundle gate assertion class #1 collapses to
# registry+URN-shape verification for these methods. Per the Phase 2a–2e
# predicate comment blocks the only rate-table touch is in Expense Payment
# /Property/Residual which consume the FY2026 `in-house-benefit-cap` rate-node
# under the in-house variant; assertion class #1 will fire for those.
#
# Per CLAWDOG/110 §3.3 (atom-vs-bridge boundary): jurisdiction (AU) lives on
# the registry entry, NOT smuggled into the URN or any field. fbt_type is
# echoed unchanged by the engine (Type 1 vs Type 2 is a gross-up concern,
# not a per-calculator algebraic concern).


class FBTLoanInput(BaseModel):
    """Input for Phase 2a Loan Fringe Benefit (engine: ``calculate_fbt_loan_benefit_type_2``).

    FBTAA Division 4 (ss.16–19). Engine arithmetic at FBT_Engine.pl L2434.
    ``fbt_benchmark_interest_amount`` is the DOLLAR amount (not the 0.0862
    rate); the rate is applied upstream by the caller against
    ``original_loan_amount`` if supplied.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    fbt_benchmark_interest_amount: float | None = Field(
        None, ge=0, alias="fbtBenchmarkInterestAmount",
        description=(
            "Benchmark FBT interest amount (AUD) per FBTAA Schedule 1. If "
            "omitted, derived from ``original_loan_amount`` × benchmark rate."
        ),
    )
    interest_charged_by_employer: float = Field(
        ..., ge=0, alias="interestChargedByEmployer",
        description="Actual interest amount the employer charged the employee (AUD).",
    )
    otherwise_deductible_percentage: float = Field(
        ..., ge=0, le=100, alias="otherwiseDeductiblePercentage",
        description="Otherwise-deductible percentage [0..100] per FBTAA s.19.",
    )
    original_loan_amount: float | None = Field(
        None, ge=0, alias="originalLoanAmount",
        description=(
            "Original loan principal (AUD); only consulted when "
            "``fbt_benchmark_interest_amount`` is absent."
        ),
    )
    fbt_type: str | None = Field(
        None, alias="fbtType",
        description="'Type 1' or 'Type 2'; defaults engine-side to 'Type 2'.",
    )


class FBTDebtWaiverInput(BaseModel):
    """Input for Phase 2b Debt Waiver Fringe Benefit (engine: ``calculate_fbt_debt_waiver``).

    FBTAA s.16. Engine arithmetic at FBT_Engine.pl L3433. Type 2 only per
    FBTAA; ``fbt_type`` echoed as 'Type 2'.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    amount_waived: float = Field(
        ..., ge=0, alias="amountWaived",
        description="Principal debt amount waived (AUD).",
    )
    interest_no_longer_charged: float | None = Field(
        None, ge=0, alias="interestNoLongerCharged",
        description=(
            "Foregone interest no longer charged following the waiver (AUD); "
            "defaults engine-side to 0."
        ),
    )


class _ExpensePaymentBaseInput(BaseModel):
    """Shared input shape for Phase 2c Expense Payment (std + in-house variants).

    FBTAA Division 5 (ss.20–24). Engine arithmetic at FBT_Engine.pl L3501.
    In-house variant consults the FY2026 ``in-house-benefit-cap`` rate-node
    per Standing Rule #6.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    expense_value: float = Field(
        ..., ge=0, alias="expenseValue",
        description="Gross expense amount paid/reimbursed by the employer (AUD).",
    )
    otherwise_deductible_percentage: float = Field(
        ..., ge=0, le=100, alias="otherwiseDeductiblePercentage",
        description="Otherwise-deductible percentage [0..100] per FBTAA s.24.",
    )
    employee_contribution: float = Field(
        0, ge=0, alias="employeeContribution",
        description="Employee contribution toward the expense (AUD); clamped at gross.",
    )
    inhouse_benefit_claimed: float | None = Field(
        None, ge=0, alias="inhouseBenefitClaimed",
        description=(
            "In-house benefit reduction claimed (AUD); only consulted on the "
            "in-house variant; clamped to FY2026 in-house cap (FBTAA s.62)."
        ),
    )
    fbt_type: str | None = Field(
        None, alias="fbtType",
        description="'Type 1' or 'Type 2'; defaults engine-side to 'Type 2'.",
    )


class FBTExpensePaymentInput(_ExpensePaymentBaseInput):
    """Phase 2c std Expense Payment."""


class FBTExpensePaymentInHouseInput(_ExpensePaymentBaseInput):
    """Phase 2c in-house Expense Payment (consumes ``in-house-benefit-cap``)."""


class _PropertyBaseInput(BaseModel):
    """Shared input shape for Phase 2d Property (std + in-house variants).

    FBTAA Division 7 (ss.40–44). Engine arithmetic at FBT_Engine.pl L3640.
    In-house variant consults the FY2026 ``in-house-benefit-cap`` rate-node.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    gst_inclusive_value: float = Field(
        ..., ge=0, alias="gstInclusiveValue",
        description="GST-inclusive value of the property benefit (AUD).",
    )
    otherwise_deductible_percentage: float = Field(
        ..., ge=0, le=100, alias="otherwiseDeductiblePercentage",
        description="Otherwise-deductible percentage [0..100] per FBTAA s.44.",
    )
    employee_contribution: float = Field(
        0, ge=0, alias="employeeContribution",
        description="Employee contribution toward the property (AUD).",
    )
    inhouse_benefit_claimed: float | None = Field(
        None, ge=0, alias="inhouseBenefitClaimed",
        description=(
            "In-house benefit reduction claimed (AUD); only consulted on the "
            "in-house variant; clamped to FY2026 in-house cap (FBTAA s.62)."
        ),
    )
    fbt_type: str | None = Field(
        None, alias="fbtType",
        description="'Type 1' or 'Type 2'; defaults engine-side to 'Type 2'.",
    )


class FBTPropertyInput(_PropertyBaseInput):
    """Phase 2d std Property."""


class FBTPropertyInHouseInput(_PropertyBaseInput):
    """Phase 2d in-house Property (consumes ``in-house-benefit-cap``)."""


class _ResidualBaseInput(BaseModel):
    """Shared input shape for Phase 2e Residual (std + in-house variants).

    FBTAA Division 12 (ss.45–52). Engine arithmetic at FBT_Engine.pl L3763.
    In-house variant consults the FY2026 ``in-house-benefit-cap`` rate-node.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    gst_inclusive_value: float = Field(
        ..., ge=0, alias="gstInclusiveValue",
        description="GST-inclusive value of the residual benefit (AUD).",
    )
    otherwise_deductible_percentage: float = Field(
        ..., ge=0, le=100, alias="otherwiseDeductiblePercentage",
        description="Otherwise-deductible percentage [0..100] per FBTAA s.52.",
    )
    employee_contribution: float = Field(
        0, ge=0, alias="employeeContribution",
        description="Employee contribution toward the residual benefit (AUD).",
    )
    inhouse_benefit_claimed: float | None = Field(
        None, ge=0, alias="inhouseBenefitClaimed",
        description=(
            "In-house benefit reduction claimed (AUD); only consulted on the "
            "in-house variant; clamped to FY2026 in-house cap (FBTAA s.62)."
        ),
    )
    fbt_type: str | None = Field(
        None, alias="fbtType",
        description="'Type 1' or 'Type 2'; defaults engine-side to 'Type 2'.",
    )


class FBTResidualInput(_ResidualBaseInput):
    """Phase 2e std Residual."""


class FBTResidualInHouseInput(_ResidualBaseInput):
    """Phase 2e in-house Residual (consumes ``in-house-benefit-cap``)."""


# =============================================================================
# Wave B — Phase 2f–2i public-API widening (mut-2026-05-31-mc17)
# =============================================================================
#
# 4 method-atom input schemas wrapping the Phase 2f–2i Prolog predicates in
# LodgeiT_FBT. Engine reference: FBT_Engine.pl L2586 (Board) / L2761 (Housing)
# / L2943 (LAFHA) / L3089 (TEBE) at LodgeiT_FBT `81e1a0ff`.
#
# Sheet-parity carry-overs from the FBT Phase 2 sprint (mut-2026-05-31-mc05 +
# mc07 + mc09 + mc10):
# - Board: sheet row 35 ($350) DIVERGES from statute-correct ($5,300); OT #94
#   Waqas-clarification WAIT-STATE. Predicate is statute-faithful (see
#   findings/FBT_BOARD_SHEET_DIVERGENCE.md).
# - Housing: clean ship; both sheet cases reproduce statute-correct.
# - LAFHA: clean ship; the engine expects the caller to supply the
#   pre-computed scalar exempt_food_component (TD 2025/2 composition lookup
#   is sheet/UI concern).
# - TEBE: clean ship; s.39 expenditure-passthrough; 50/50-split method is a
#   sheet/UI-layer caller-side concern, not engine.


class FBTBoardInput(BaseModel):
    """Input for Phase 2h Board Fringe Benefit (engine: ``calculate_fbt_board``).

    FBTAA s.36 (Compilation No. 95). Engine arithmetic at FBT_Engine.pl L2586.
    Type 2 only. Sheet row 35 sheet-vs-statute divergence is parked under
    OT #94; the predicate is statute-faithful.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    members_under_twelve: int | None = Field(
        0, ge=0, alias="membersUnderTwelve",
        description="Number of family members under 12 years (s.36(c)(i)).",
    )
    under_12_meals_per_child: int | None = Field(
        0, ge=0, alias="under12MealsPerChild",
        description="Meals provided per under-12 family member during the FBT year.",
    )
    members_over_twelve: int | None = Field(
        0, ge=0, alias="membersOverTwelve",
        description="Number of employees/associates aged 12 or over (s.36(c)(ii)).",
    )
    over_12_meals_per_child: int | None = Field(
        0, ge=0, alias="over12MealsPerChild",
        description="Meals provided per 12+ employee/associate during the FBT year.",
    )
    over_12_employee_contributions: float | None = Field(
        0, ge=0, alias="over12EmployeeContributions",
        description="Total employee contributions toward 12+ meals (AUD).",
    )


class FBTHousingInput(BaseModel):
    """Input for Phase 2f Non-Remote Housing Fringe Benefit (engine: ``calculate_fbt_housing``).

    FBTAA s.26(1)(c) + s.26(2)(b). Engine arithmetic at FBT_Engine.pl L2761.
    Indexation factor is period-scoped per s.26(2)(b); FY2026 published State
    rates span 0.988 (TAS) to 1.100 (WA). C# range-clamp [0.001, 1.099] under-
    indexes WA — mirrored here for parity (banked forward concern OT #95
    sibling).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    housing_benefit_value: float = Field(
        ..., ge=0, alias="housingBenefitValue",
        description="Statutory annual value of the housing right at start of FBT year (AUD).",
    )
    indexation_factor: float | None = Field(
        1.0, ge=0, alias="indexationFactor",
        description=(
            "State indexation factor per FBTAA s.26(2)(b). "
            "Out-of-range values (less than 0.001 or greater than 1.099) "
            "reset to 1.0 per C# clamp (under-indexes WA's 1.100)."
        ),
    )
    recipient_rent: float | None = Field(
        0, ge=0, alias="recipientRent",
        description="Rent paid by recipient to employer (AUD); reduces taxable value.",
    )
    fbt_type: str | None = Field(
        None, alias="fbtType",
        description="'Type 1' or 'Type 2'; defaults engine-side to 'Type 2'.",
    )


class FBTLafhaInput(BaseModel):
    """Input for Phase 2g LAFHA Fringe Benefit (engine: ``calculate_fbt_lafha``).

    FBTAA s.31(2). Engine arithmetic at FBT_Engine.pl L2943. Always Type 2 per
    ATO TR 96/9. ``exempt_food_component`` is the pre-computed scalar (TD 2025/2
    composition lookup is sheet/UI-layer concern).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    weeks_lived_away: float = Field(
        ..., ge=0, alias="weeksLivedAway",
        description="Number of weeks the employee lived away from home.",
    )
    accommodation_per_week: float = Field(
        ..., ge=0, alias="accommodationPerWeek",
        description="Accommodation allowance paid per week (AUD).",
    )
    meals_per_week: float = Field(
        ..., ge=0, alias="mealsPerWeek",
        description="Food/drink allowance paid per week (AUD).",
    )
    exempt_accommodation_component: float | None = Field(
        0, ge=0, alias="exemptAccommodationComponent",
        description=(
            "Total exempt accommodation component per s.31(2)(a) (AUD; not weekly)."
        ),
    )
    exempt_food_component: float | None = Field(
        0, ge=0, alias="exemptFoodComponent",
        description=(
            "Total exempt food component per s.31(2)(b) (AUD; not weekly). "
            "Caller computes via TD 2025/2 composition lookup; engine consumes scalar."
        ),
    )


class FBTTebeInput(BaseModel):
    """Input for Phase 2i Tax-Exempt Body Entertainment (engine: ``calculate_fbt_tebe``).

    FBTAA Subdivision B of Division 10 (ss.38–39). Engine arithmetic at
    FBT_Engine.pl L3089. s.39 is a thin expenditure-passthrough statute.
    50/50-split method is a sheet/UI-layer caller concern (the caller supplies
    the post-50/50 totals; engine sums).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    salary_packaged_meal_efle: float = Field(
        ..., ge=0, alias="salaryPackagedMealEfle",
        description=(
            "Total expenditure on salary-packaged meal entertainment + EFLE "
            "for tax-exempt body employees (AUD)."
        ),
    )
    recreation: float = Field(
        ..., ge=0, alias="recreation",
        description="Total recreation entertainment expenditure (AUD).",
    )
    fbt_type: str | None = Field(
        None, alias="fbtType",
        description=(
            "'Type 1' (creditable acquisitions) or 'Type 2' (input-taxed); "
            "defaults engine-side to 'Type 2'."
        ),
    )


class ManifestRateTableEntry(BaseModel):
    """One entry in the manifest's ``rate_table_uris`` block (CLAWDOG/109 §7.1)."""

    model_config = ConfigDict(extra="forbid")

    uri: str
    content_hash: str = Field(..., min_length=64, max_length=64)
    hash_algorithm: str = Field("sha256")

    @field_validator("uri")
    @classmethod
    def _validate_uri(cls, v: str) -> str:
        if not _RATE_URI_RE.match(v):
            raise ValueError(
                f"uri={v!r} is not a valid SBRM rate URI shape "
                f"(urn:sbrm:rate:<calc>:<period_id>:<rate_id>)."
            )
        return _reject_smuggling(v, "uri")

    @field_validator("content_hash")
    @classmethod
    def _validate_hex(cls, v: str) -> str:
        if not re.match(r"^[0-9a-f]{64}$", v):
            raise ValueError("content_hash must be a 64-char lowercase hex SHA-256.")
        return v


class Manifest(BaseModel):
    """``manifest`` block — CLAWDOG/109 §7.1 Manifest-Fidelity Contract."""

    model_config = ConfigDict(extra="forbid")

    rate_table_uris: list[ManifestRateTableEntry]


class AdvisoryBlock(BaseModel):
    """``advisory`` block — CLAWDOG/109 §6 / CLAWDOG/110 §3.2."""

    model_config = ConfigDict(extra="allow")

    disclaimer: str = Field(..., min_length=1)
    registered_agent_required: bool
    statutory_basis: list[dict[str, str]]
    jurisdiction: str


class CalculatorInvocationResponse(BaseModel):
    """Standard wire shape for any calculator invocation response."""

    model_config = ConfigDict(extra="allow")

    taxable_value: float
    trace: dict[str, Any]
    manifest: Manifest
    advisory: AdvisoryBlock


class CalculatorListing(BaseModel):
    """One entry in the calculator-discovery listing (GET /v1/calculators)."""

    model_config = ConfigDict(extra="forbid")

    calc_uri: str
    label: str
    method: str
    supported_periods: list[str]
    input_schema_ref: str
    jurisdiction: str


def validate_period_uri(period_uri: str) -> str:
    """Validate a period URI path-parameter (atom-vs-bridge gate)."""
    if not _PERIOD_URI_RE.match(period_uri):
        raise ValueError(
            f"period_uri={period_uri!r} is not a valid SBRM period URI "
            f"(urn:sbrm:period:<calc>:<period_id>)."
        )
    return _reject_smuggling(period_uri, "period_uri")


def validate_calc_uri(calc_uri: str) -> str:
    """Validate a calculator URI path-parameter (atom-vs-bridge gate)."""
    if not _CALC_URI_RE.match(calc_uri):
        raise ValueError(
            f"calc_uri={calc_uri!r} is not a valid SBRM/lodgeit calculator URI."
        )
    return _reject_smuggling(calc_uri, "calc_uri")


__all__ = [
    "FBTCarOperatingCostInput",
    # Wave A (Phase 2a–2e) public-API widening (mut-2026-05-31-mc15)
    "FBTLoanInput",
    "FBTDebtWaiverInput",
    "FBTExpensePaymentInput",
    "FBTExpensePaymentInHouseInput",
    "FBTPropertyInput",
    "FBTPropertyInHouseInput",
    "FBTResidualInput",
    "FBTResidualInHouseInput",
    # Wave B (Phase 2f–2i) public-API widening (mut-2026-05-31-mc17)
    "FBTHousingInput",
    "FBTLafhaInput",
    "FBTBoardInput",
    "FBTTebeInput",
    "ManifestRateTableEntry",
    "Manifest",
    "AdvisoryBlock",
    "CalculatorInvocationResponse",
    "CalculatorListing",
    "validate_period_uri",
    "validate_calc_uri",
]
