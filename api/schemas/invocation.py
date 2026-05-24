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
    "ManifestRateTableEntry",
    "Manifest",
    "AdvisoryBlock",
    "CalculatorInvocationResponse",
    "CalculatorListing",
    "validate_period_uri",
    "validate_calc_uri",
]
