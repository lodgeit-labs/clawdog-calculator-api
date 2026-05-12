"""Depreciation calculator pydantic schemas.

Phase 3c.3.B (Andrew + Tracer ratified 2026-05-12 05:54 UTC) onboards the
Depreciation calculator's `/api/v1/depreciation/audit` Prolog endpoint
through the REST surface per Option α (minimum-viable; CLAWDOG/109 §8.3
abstraction-leak test data point).

Engine context (per Andrew 2026-05-12 05:54 UTC):
    Our accounting engine supports prime cost + diminishing value only.
    The /audit endpoint cross-checks ledger-side accumulated depreciation
    against straight-line / DV ideals so accountants can spot variance
    between LodgeiT tax-depreciation (often accelerated via IAWO/pool)
    and the more conservative accounting-side method. /resurrect and
    /adjustment_journal are upstream/downstream pipeline shapes; both
    out of scope for β.2.B.

Atom-vs-bridge boundary (CLAWDOG/110 §3.3): per-asset fields are atom-pure
carriers. The audit interpretation (variance threshold, method-flag
warning, Hoffman-Seattle modal types) lives in the Prolog engine; this
schema only ferries identity-carrying values across the bridge.

Standing Rule #6 (Hoffman Temporal-Dimension Discipline): every audit
request carries a `transition_date` that anchors the audit to a point in
time. Period URI in the URL path; transition_date in the body.

Phase 3c.4 will generalise the FBT-shaped PrologClient + invoke route
into a calc-uri-dispatched shape that covers both FBT and Depreciation
cleanly. This schema is built to slot into that generalisation without
breaking shape.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- Per-asset input ---------------------------------------------------------

# ISO-8601 calendar date (no time component).
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DepreciationAuditAssetInput(BaseModel):
    """One asset row in a depreciation-audit batch.

    Mirrors the upstream Prolog handler's accepted shape
    (`app/server/depreciation_server.pl::handle_audit`); fields are
    atom-pure carriers of identity per CLAWDOG/110 §3.3.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    asset_id: str = Field(
        ..., alias="assetId",
        description="Caller-supplied stable identifier for the asset row.",
    )
    asset_name: str = Field(
        ..., alias="assetName",
        description=(
            "Free-text asset description. Used by the Prolog Tier-1 classifier "
            "(keyword_map/2 + Stopwords.pl) to resolve effective-life category."
        ),
    )
    purchase_date: str = Field(
        ..., alias="purchaseDate",
        description="ISO-8601 date of acquisition (e.g. 2015-01-30).",
    )
    original_cost: float = Field(
        ..., ge=0, alias="originalCost",
        description="Acquisition cost (AUD).",
    )
    tax_method: str = Field(
        ..., alias="taxMethod",
        description=(
            "The depreciation method historically applied on the tax side. "
            "Common values: 'dv' (diminishing value), 'pc' (prime cost). "
            "Used by the engine to surface a method-flag warning when the "
            "accounting-side ideal differs from the tax-side recorded method."
        ),
    )
    current_book_accum_dep: float = Field(
        ..., ge=0, alias="currentBookAccumDep",
        description=(
            "Current ledger-side accumulated depreciation balance at the "
            "transition date (AUD). The audit compares this against the "
            "ideal-method projection to detect material variance."
        ),
    )

    @field_validator("purchase_date")
    @classmethod
    def _check_iso_date(cls, value: str) -> str:
        if not _ISO_DATE_RE.match(value):
            raise ValueError(
                f"purchase_date={value!r} is not ISO-8601 YYYY-MM-DD. "
                f"Convert at the client boundary; the engine does not "
                f"parse other date shapes."
            )
        return value


# --- Top-level input ---------------------------------------------------------


class DepreciationAuditInput(BaseModel):
    """Input for the Depreciation Audit endpoint.

    Wire-shape mirrors the upstream Prolog `/api/v1/depreciation/audit`
    handler: a transition_date, a method discriminator, and an
    `assets_to_audit` batch.

    The `method` field is constrained to the accounting-engine scope per
    Andrew (2026-05-12 05:54 UTC): prime cost + diminishing value only.
    The engine's `normalize_method/2` accepts `'dvmethod'` for DV; legacy
    aliases on input are coerced to canonical strings before forwarding.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    transition_date: str = Field(
        ..., alias="transitionDate",
        description=(
            "ISO-8601 date marking the audit anchor (e.g. 2025-07-01 = "
            "FY2026 opening). The engine projects accumulated depreciation "
            "to this date and compares against current_book_accum_dep."
        ),
    )
    method: Literal["primecost", "dvmethod"] = Field(
        "primecost", alias="method",
        description=(
            "Accounting-side ideal method to project. 'primecost' = "
            "straight-line; 'dvmethod' = diminishing value. The engine "
            "default is 'primecost' (matches handle_audit fall-through)."
        ),
    )
    assets_to_audit: list[DepreciationAuditAssetInput] = Field(
        ..., min_length=1, alias="assetsToAudit",
        description=(
            "Batch of asset rows to audit. The engine processes them "
            "sequentially; total runtime is dominated by Tier-1 classifier "
            "lookups (keyword_map/2)."
        ),
    )

    @field_validator("transition_date")
    @classmethod
    def _check_iso_date(cls, value: str) -> str:
        if not _ISO_DATE_RE.match(value):
            raise ValueError(
                f"transition_date={value!r} is not ISO-8601 YYYY-MM-DD."
            )
        return value


# --- Output ------------------------------------------------------------------
#
# Note: the depreciation Prolog `/audit` endpoint returns a heterogeneous
# response shape including a list of per-asset audit reports with
# Hoffman-Seattle modal types embedded. Phase 3c.3.B does NOT reshape
# that response in the bridge — it is forwarded with `extra="allow"` so
# downstream consumers see the engine's native shape unchanged. Phase
# 3c.4 (PrologClient generalisation) can decide whether to typed-wrap
# this; for now the discipline is "no reshape across the bridge"
# (CLAWDOG/110 §3.3 atom-vs-bridge — interpretation lives in the engine,
# not the API).


class DepreciationAuditPerAssetReport(BaseModel):
    """One per-asset audit report. Permissive shape — engine adds fields."""

    model_config = ConfigDict(extra="allow")


class DepreciationAuditResponse(BaseModel):
    """Envelope for the depreciation /audit response.

    Mirrors the engine's `_{status, transition_date, method, audited_standard_assets}`
    dict, wrapped with the standard manifest + advisory blocks per
    CLAWDOG/109 §6 / §7.
    """

    model_config = ConfigDict(extra="allow")

    status: str
    transition_date: str
    method: str
    audited_standard_assets: list[dict[str, Any]]
    # manifest + advisory injected by api.lib.advisory_boundary.wrap_response
