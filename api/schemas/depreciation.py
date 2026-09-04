"""Pydantic input + response models for the depreciation-engine wire boundary.

mc39-2026-08-29 rung 5 (Fable verdict amendment 2 §A2.8): the batch-audit
model (`DepreciationAuditInput` + `DepreciationAuditAssetInput` +
`DepreciationAuditResponse` + `DepreciationAuditPerAssetReport`) has been
REMOVED and superseded by the single-asset point-in-time model
(`DepreciationAtInput` + `DepreciationAtResponse`) mirroring the T6
depreciation-engine wire exactly.

**Fable rider 1 (§A2.4):** gateway constrains `basis` to the AU literals
(`accounting`, `tax`, `au_itaa97`, `au_aasb116`). The engine's fifth
literal `uk_frs102_s17` is refused at the gateway with a typed refusal
(gateway registry `jurisdiction: "AU"` remains true; UK becomes its own
registry entry the day someone wants it).

**Fable rider 2 (§A2.4):** gateway pins `numeric_mode: "serving"` and does
not expose the field. Corpus-compare is a T6 regression-testing knob for
internal LodgeiT-parity discipline; not a partner-developer affordance.

**Fable rider 3 (§A2.4):** T6 pool exclusion surfaced in the gateway
manifest (see `_CALCULATOR_REGISTRY[urn:sbrm:calculator:depreciation:at]`
manifest text in `api/routes/calculators.py`); the engine's typed refusal
(`refusal_class="pool_asset_out_of_t6_scope"`) is passed through cleanly
rather than flattened to a generic 400.

Sibling shape: Div7A_Engine `Div7aAtInput` (mut-2026-08-24-mc20 mirror
pattern; extra="forbid" + templated period_uri path + basis-conditional
field validation deferred to the engine which is F13 UPHELD schema-layer
authority).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# D8a defence-in-depth: basis-conditional field validation at the gateway.
#
# Fable post-matrix directive mc00-2026-09-04 D8a defence-in-depth ruling:
#
#   "Add gateway-side conditional validation as defence in depth so the
#    engine is not reached for a caller error — but the mapper is the
#    safety net and it ships first, because the next conditional rule the
#    engine grows would otherwise reintroduce this."
#
# This helper mirrors the CURRENTLY-KNOWN set of engine basis-conditional
# rules (F13 UPHELD: engine remains authoritative on the full set). If a
# caller omits a basis-conditional field, they get a 422 at the pydantic
# layer with the missing field named, rather than a round-trip to the engine
# followed by the mapper's engine_validation_error surface. Two boundaries,
# one for latency + charity to the caller, one for correctness:
#
#   Gateway pydantic (this helper) — catches KNOWN engine rules.
#     Miss surfaces as: gateway 422 (fast, actionable).
#
#   Central engine-error mapper §1b — catches UNKNOWN engine rules that
#     the gateway did not yet learn about (schema drift).
#     Miss surfaces as: gateway 422 + `gateway_engine_schema_drift`
#     warning log line (Fable Amendment 3 drift-detector).
#
# Rule set (as of engine mc-2026-09-03 wire probe):
#
#   basis="accounting" REQUIRES asset.accounting_useful_life_years
#                      REQUIRES asset.accounting_method
#                      REFUSES  asset.tax_asset_class
#
#   basis="tax"        REQUIRES asset.tax_asset_class
#                      REFUSES  asset.accounting_useful_life_years
#                      REFUSES  asset.accounting_method
#
# When the engine grows a NEW rule (e.g. `basis="au_aasb116"` gains a
# unique required field), the engine's own 422 will fire, land on the
# mapper's 422 branch, emit `gateway_engine_schema_drift`, and Andrew sees
# the drift as a distinct log line rather than a silent gateway-passed
# malformed request. The path to fix is to add the rule here.


def _validate_basis_conditional_asset_fields(
    basis: str,
    asset_dict: dict,
) -> None:
    """Raise ValueError with a caller-actionable message when the asset
    payload does not satisfy the KNOWN basis-conditional rules.

    Called from model_validators on both `DepreciationAtInput` and
    `DepreciationRangeInput`. The message shape mirrors the engine's own
    422 detail string (`"basis='X' requires 'asset.Y'"`) so a caller
    testing against the engine directly and against the gateway sees
    equivalent text.
    """
    if asset_dict is None:
        return  # nested pydantic will emit its own 422

    if basis == "accounting":
        missing = []
        if asset_dict.get("accounting_useful_life_years") is None:
            missing.append("asset.accounting_useful_life_years")
        if asset_dict.get("accounting_method") is None:
            missing.append("asset.accounting_method")
        if missing:
            raise ValueError(
                f"basis='accounting' requires {' + '.join(missing)}"
            )
        # Cross-field refusal: tax_asset_class must NOT be present on
        # accounting basis. Silent acceptance would produce a payload
        # the engine currently refuses; we surface it at the gateway.
        if asset_dict.get("tax_asset_class") is not None:
            raise ValueError(
                "basis='accounting' refuses 'asset.tax_asset_class' "
                "(tax_asset_class is a tax-basis field; the engine's fold "
                "will refuse mixing bases)"
            )
    elif basis == "tax":
        if asset_dict.get("tax_asset_class") is None:
            raise ValueError(
                "basis='tax' requires 'asset.tax_asset_class'"
            )
        # Cross-field refusal on the other direction.
        extra_accounting = []
        if asset_dict.get("accounting_useful_life_years") is not None:
            extra_accounting.append("asset.accounting_useful_life_years")
        if asset_dict.get("accounting_method") is not None:
            extra_accounting.append("asset.accounting_method")
        if extra_accounting:
            raise ValueError(
                f"basis='tax' refuses {' + '.join(extra_accounting)} "
                f"(accounting-basis fields; the engine's fold will refuse "
                f"mixing bases)"
            )
    # No conditional rules known for other basis values. When D8c narrows
    # to accounting-only the `elif basis == "tax"` branch becomes dead
    # code but stays here as a design record until the engine drops the
    # tax basis or a UK basis lands with its own rules.

# Gateway-scoped basis literals per Fable rider 1: engine's five-literal
# vocabulary narrowed to AU-only. `uk_frs102_s17` refused at the pydantic
# layer so the gateway wire self-describes as AU-jurisdiction consistently.
# Narrowed 2026-08-30: the engine declares five basis literals but computes
# only two. `au_itaa97`, `au_aasb116` and `uk_frs102_s17` pass the engine's own
# validation and then raise MissingAssetCreatedFieldError in the fold, so the
# gateway advertises only what returns a number. Widen again once the engine
# wires the explicit framework literals through basis_registry.
GatewayBasisLiteral = Literal[
    "accounting",     # AASB 116 useful-life basis (engine-verified 2026-08-30)
    "tax",            # ATO Div 40 basis (engine-verified 2026-08-30)
]


# Fable D4 mc17 2026-09-03 12:20 UTC + D5 mc02 2026-09-04 01:19 UTC:
# day_count vocabulary matches the engine's DayCountLiteral post-D4.
# `actual/actual` promoted to the recommended default for basis:
# accounting (anniversary-scoped denominator; AASB 116-faithful;
# each period charges exactly cost/life; asset lands on zero at
# life-end). `actual/365` retained honest at the label; a leap-
# spanning year yields 366/365 = 1.00274 * (cost/life) which is
# the 5.48 over-charge Fable's D4 probes surfaced. `monthly` uses
# per-month round-and-sum for ledger reconciliation (each month
# quantised BEFORE summation; range_dep is the sum of monthly
# journal figures a caller would post).
DayCountLiteral = Literal["actual/actual", "actual/365", "monthly"]


AccountingMethodLiteral = Literal["prime_cost", "diminishing_value"]


class AssetCreatedInput(BaseModel):
    """Asset ingestion input (mirrors engine's `AssetCreatedInput`).

    F10 amendment: `acquisition_date` is required (non-optional). Basis-
    conditional fields (`accounting_useful_life_years` + `accounting_method`
    when basis is accounting; `tax_asset_class` when basis is tax) are
    validated at the engine's schema layer (F13 UPHELD) rather than
    duplicated here; the gateway forwards the payload verbatim and lets the
    engine return the typed refusal on inconsistency.
    """

    model_config = ConfigDict(extra="forbid")

    cost: Annotated[
        Decimal,
        Field(
            gt=0,
            description=(
                "Initial cost basis. Positive Decimal; SR #3 fail-loud "
                "rejects zero or negative."
            ),
        ),
    ]

    acquisition_date: Annotated[
        date,
        Field(
            description=(
                "Asset acquisition date. Required per F10 amendment; "
                "determines fiscal-year placement + calculation_start "
                "record emission at fold entry."
            ),
        ),
    ]

    # Accounting-basis fields (populated when basis='accounting' or
    # 'au_aasb116'; validated at engine schema layer).
    accounting_useful_life_years: Annotated[
        int | None,
        Field(
            default=None,
            gt=0,
            description=(
                "Accounting useful life in years. Required when "
                "basis is 'accounting' or 'au_aasb116'; must be omitted "
                "when basis is 'tax' or 'au_itaa97' (tax path resolves "
                "effective_life from the SBRM rate table)."
            ),
        ),
    ] = None

    accounting_method: Annotated[
        AccountingMethodLiteral | None,
        Field(
            default=None,
            description=(
                "Accounting depreciation method. Required when basis is "
                "'accounting' or 'au_aasb116'. Values: 'prime_cost' "
                "(straight-line) or 'diminishing_value'."
            ),
        ),
    ] = None

    # Tax-basis field (populated when basis='tax' or 'au_itaa97';
    # validated at engine schema layer).
    tax_asset_class: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Tax asset class URI resolving to a rate-table effective-life "
                "entry. Required when basis is 'tax' or 'au_itaa97'; must be "
                "omitted when basis is 'accounting' or 'au_aasb116'."
            ),
        ),
    ] = None

    # F2-α field (RATIFIED mc11-2026-08-31; ratifying-doc
    # `memory/proposals/2026-08-31-depreciation-product-scope-RATIFIED.md`
    # §2 Ask 2 revised at mc12 §9.d): `dv_rate_factor` was previously
    # excluded by `extra="forbid"`, which made diminishing-value method
    # unreachable through the gateway (rung 5 case 6a returned HTTP 422
    # `extra_forbidden`; 6b returned HTTP 502 engine_unavailable). Field is
    # now declared at the gateway so the payload reaches the engine; the
    # conditional validation ("required when accounting_method='diminishing_value'")
    # stays at the engine's schema layer per F13 UPHELD schema-authority.
    dv_rate_factor: Annotated[
        Decimal | None,
        Field(
            default=None,
            gt=0,
            description=(
                "Diminishing-value rate factor as a multiplier of 1/life. "
                "ATO Div 40 default is 2 (200% method); prime-cost equivalent "
                "is 1. REQUIRED at the engine when accounting_method is "
                "'diminishing_value'; conditional validation is enforced at "
                "the engine schema layer per F13 UPHELD (the gateway does not "
                "duplicate). MUST be omitted when accounting_method is "
                "'prime_cost'. Unit convention: rate factor (e.g. 2.0 for the "
                "200% method), NOT the resulting per-year rate."
            ),
        ),
    ] = None

    # F2-β field (RATIFIED mc11-2026-08-31 §2 Ask 2 CONDITIONAL revised at
    # mc12 10:38 UTC to UNCONDITIONAL): `pool_type` was previously excluded
    # by `extra="forbid"`, which meant a pooled asset received a generic
    # `extra_forbidden` schema error rather than the typed
    # `pool_asset_out_of_t6_scope` refusal the manifest promises. Rider 3
    # typed-refusal passthrough (rung 5 case 7 wire-verified via depreciation
    # route's `refusal_class`-preserving 400 branch) makes the manifest
    # exclusion demonstrable rather than aspirational. Conditional validation
    # ("pool_type is refused by the engine's D2 fold with typed refusal_class
    # `pool_asset_out_of_t6_scope`") stays at the engine per F13 UPHELD;
    # gateway accepts the field so the payload reaches the engine and the
    # typed refusal fires.
    pool_type: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Pool membership discriminator. Any non-null value is refused "
                "by the engine's D2 fold with typed refusal_class "
                "'pool_asset_out_of_t6_scope' (rider 3 passthrough: gateway "
                "returns HTTP 400 with refusal envelope preserved rather than "
                "flattening to 502). T6 first-cut scope is single asset only; "
                "pool machinery lands in the T6.1 pool-retrofit sprint. "
                "Documented exclusion in the manifest is now wire-demonstrable "
                "because the field reaches the engine's typed refusal path."
            ),
        ),
    ] = None


class EventInput(BaseModel):
    """Per-asset lifecycle event (mirrors engine's `EventInput`).

    Events layer on top of `asset` at construction and let the fold
    reconstitute the WDV trajectory. Engine caps events at 10 000 items per
    request (F19 item 12); the gateway does not re-validate that cap here
    since the engine's schema layer is authoritative.
    """

    model_config = ConfigDict(extra="forbid")

    event_type: Annotated[
        Literal[
            "cost_addition",
            "useful_life_reassessment",
            "opening_balance",
        ],
        Field(description="F19 item 13 frozen event vocabulary."),
    ]

    event_date: Annotated[
        date,
        Field(description="Effective date of the event."),
    ]

    # Optional per-event fields; engine schema layer validates conditional
    # requiredness per event_type.
    cost_delta: Annotated[
        Decimal | None,
        Field(
            default=None,
            description="Cost addition amount for event_type='cost_addition'.",
        ),
    ] = None

    new_useful_life_years: Annotated[
        int | None,
        Field(
            default=None,
            gt=0,
            description=(
                "Reassessed useful life for "
                "event_type='useful_life_reassessment'."
            ),
        ),
    ] = None

    opening_balance_amount: Annotated[
        Decimal | None,
        Field(
            default=None,
            description=(
                "Opening balance for event_type='opening_balance'."
            ),
        ),
    ] = None


class DepreciationAtInput(BaseModel):
    """Request body for the gateway's depreciation `at` route.

    Wire-shape mirrors the upstream depreciation-engine
    `/v1/calculators/depreciation/at/{period_uri}` endpoint (Fable F1 UPHELD
    mc11-2026-08-02 URN parity). Gateway-side amendments per Fable verdict
    amendment 2 §A2.4 riders 1-2:

      * Rider 1: `basis` narrowed to AU literals; UK is refused.
      * Rider 2: `numeric_mode` is NOT a caller-visible field; the gateway
        pins the engine to `numeric_mode="serving"` internally.

    Basis-conditional field validation (which `asset` fields must be present
    given the `basis` value) is enforced at the engine's schema layer per
    F13 UPHELD; the gateway does not duplicate that validation.
    """

    model_config = ConfigDict(extra="forbid")

    basis: Annotated[
        GatewayBasisLiteral,
        Field(
            description=(
                "Depreciation basis discriminator. Gateway rider 1 narrows "
                "the engine's five-literal vocabulary to the four AU "
                "literals: 'accounting' (AASB 116 alias), 'tax' (ITAA97 "
                "alias), 'au_aasb116' (explicit AAS), 'au_itaa97' "
                "(explicit ATO Div 40). UK framework 'uk_frs102_s17' is "
                "refused at this gateway; UK becomes its own registry "
                "entry when a UK consumer arrives."
            ),
        ),
    ]

    asset: Annotated[
        AssetCreatedInput,
        Field(description="Single-asset creation input (see AssetCreatedInput)."),
    ]

    at_date: Annotated[
        date,
        Field(
            description=(
                "Query 'as at' date. WDV + period depreciation are returned "
                "as of this date; can be interior to a fiscal year "
                "(engine pro-rates per F12 amendment)."
            ),
        ),
    ]

    events: Annotated[
        list[EventInput],
        Field(
            default_factory=list,
            description=(
                "Per-asset lifecycle events (cost additions, useful-life "
                "reassessments, opening balance). Engine caps at 10 000 "
                "items per request."
            ),
        ),
    ]

    day_count: Annotated[
        DayCountLiteral | None,
        Field(
            default=None,
            description=(
                "Optional day-count convention. **Fable D4 mc17 2026-09-03 "
                "12:20 UTC:** /at/ accepts an optional `day_count`, "
                "defaulting to `actual/actual` (the fold's basis-implicit "
                "convention for `basis: \"accounting\"`; AASB 116-faithful "
                "anniversary-scoped denominator). Not required because "
                "/at/ is live in the gateway registry (F19 wire-freeze on "
                "/at/); a required field breaks integrated callers and the "
                "smoke set for no gain. The applied convention is ECHOED "
                "in the response's `day_count` field so callers can "
                "byte-verify their expectation regardless of whether they "
                "supplied it. Values: `actual/actual` | `actual/365` | "
                "`monthly`."
            ),
        ),
    ] = None

    @model_validator(mode="after")
    def _validate_basis_conditional_fields(self) -> DepreciationAtInput:
        """D8a defence-in-depth (Fable mc00-2026-09-04): catch known engine
        basis-conditional rules at the gateway pydantic layer, before the
        engine round-trip. See `_validate_basis_conditional_asset_fields`
        module-level docstring for the rule set + drift-detector
        interaction."""
        asset_dict = self.asset.model_dump() if self.asset else None
        _validate_basis_conditional_asset_fields(self.basis, asset_dict)
        return self


class DepreciationAtResponse(BaseModel):
    """Response envelope for the gateway's depreciation `at` route.

    Field passthrough of engine's `DepreciationAtResponse` extended with
    the constellation `manifest` + `advisory` blocks per mc35 Div7A
    pattern. F4 UPHELD naming preserved: `wdv_at` is tax vocabulary but
    equals carrying amount on the accounting basis (AASB 116); the field
    name is retained for internal-fold vocabulary consistency across the
    engine's D2 AccountingFold + TaxFold implementations.
    """

    model_config = ConfigDict(extra="allow")  # engine may return extra fields

    basis: Annotated[
        GatewayBasisLiteral,
        Field(description="Echoed basis from request."),
    ]

    at_date: Annotated[
        date,
        Field(description="Echoed at_date from request."),
    ]

    wdv_at: Annotated[
        Decimal,
        Field(
            description=(
                "WDV (written-down value) at at_date. WDV is tax "
                "vocabulary; on the accounting basis this equals "
                "carrying amount (AASB 116)."
            ),
        ),
    ]

    period_dep_at: Annotated[
        Decimal,
        Field(
            description=(
                "Period depreciation for the fiscal year containing "
                "at_date, computed pro-rata to at_date when at_date is "
                "interior to a FY."
            ),
        ),
    ]

    day_count: Annotated[
        DayCountLiteral,
        Field(
            description=(
                "Echoed day_count convention (Fable D4 mc17 2026-09-03 "
                "12:20 UTC + D5 mc02 D4-drift note). Callers can "
                "byte-verify their expectation; if request omitted "
                "`day_count`, this echoes the default (`actual/actual`, "
                "the fold's basis-implicit AASB 116-faithful convention). "
                "F19 additive wire-freeze honoured: this is a NEW field "
                "added to an existing response envelope; existing "
                "consumers ignoring unknown fields are unaffected. "
                "**D4 drift fix (Fable mc21 2026-09-04):** the engine "
                "gained this field on PR #21 deploy; the gateway's "
                "published openapi.json did not describe it until this "
                "PR. Named for future readers as the first drift-gate "
                "candidate."
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# Range endpoint (Fable D5 mc02 2026-09-04 sibling URN;
# RATIFIED mc11-2026-08-31 §2 Asks 1/3/4/6 wire shape).
# ---------------------------------------------------------------------------


class DepreciationRangeInput(BaseModel):
    """Request body for the gateway's depreciation `range` route.

    Wire-shape mirrors the upstream depreciation-engine
    `/v1/calculators/depreciation/range/{period_uri}` endpoint (Fable D5
    mc02 2026-09-04 sibling of `/at/`, NOT overload per RATIFIED §2
    Ask 1).

    Gateway-side amendments (same as /at/ per Fable riders 1-2):

      * Rider 1: `basis` narrowed to AU literals; UK refused.
      * Rider 2: `numeric_mode` NOT caller-visible; gateway pins
        `serving` server-side.

    **day_count is REQUIRED (no default)** per RATIFIED §2 Ask 4;
    unaffected by Fable D5. Values: `actual/actual` (recommended
    default for basis:accounting; AASB 116-faithful anniversary-
    scoped denominator; each period charges exactly cost/life) |
    `actual/365` (constant 365 denominator regardless of FY length;
    kept HONEST at the label per Andrew ratification and Fable mc17
    D4 ruling) | `monthly` (per-month round-and-sum for ledger
    reconciliation).

    Endpoint semantics per RATIFIED §2 Ask 3:
    - INCLUSIVE of both endpoints (1 to 31 August is 31 days)
    - Zero-day range (`from_date == to_date`) returns `range_dep = 0.00`
    """

    model_config = ConfigDict(extra="forbid")

    basis: Annotated[
        GatewayBasisLiteral,
        Field(description="Basis discriminator (same vocabulary as /at/)."),
    ]

    asset: Annotated[
        AssetCreatedInput,
        Field(description="Asset creation input (nested; same as /at/)."),
    ]

    from_date: Annotated[
        date,
        Field(
            description=(
                "Range start date, INCLUSIVE. Per RATIFIED §2 Ask 3: a "
                "request with `from_date=2023-08-01` and `to_date=2023-08-31` "
                "computes for 31 days (the whole of August). If "
                "`from_date > to_date` the request is rejected at "
                "schema-layer 422."
            ),
        ),
    ]

    to_date: Annotated[
        date,
        Field(
            description=(
                "Range end date, INCLUSIVE. Zero-day range "
                "(`from_date == to_date`) returns `range_dep = 0.00` not "
                "an error."
            ),
        ),
    ]

    day_count: Annotated[
        DayCountLiteral,
        Field(
            description=(
                "REQUIRED (no default per RATIFIED §2 Ask 4). Values: "
                "`actual/actual` (recommended default for basis:accounting; "
                "AASB 116-faithful; each period charges exactly cost/life; "
                "asset lands on zero at life-end); `actual/365` (constant "
                "365 denominator regardless of FY length; leap-anniversary "
                "over-charge = the D4 defect anchor); `monthly` (per-month "
                "round-and-sum for ledger reconciliation)."
            ),
        ),
    ]

    events: Annotated[
        list[EventInput],
        Field(
            default_factory=list,
            description=(
                "Per-asset lifecycle events (same as /at/; engine caps "
                "at 10 000 items)."
            ),
        ),
    ]

    @model_validator(mode="after")
    def _validate_basis_conditional_fields(self) -> DepreciationRangeInput:
        """D8a defence-in-depth (Fable mc00-2026-09-04): shared helper with
        DepreciationAtInput. See `_validate_basis_conditional_asset_fields`
        module-level docstring."""
        asset_dict = self.asset.model_dump() if self.asset else None
        _validate_basis_conditional_asset_fields(self.basis, asset_dict)
        return self


class DepreciationRangeResponse(BaseModel):
    """Response envelope for the gateway's depreciation `range` route.

    Field passthrough of engine's `DepreciationRangeResponse` extended
    with `manifest` + `advisory` blocks per mc35 Div7A wrap pattern.

    Ledger vocabulary (Andrew mc10-2026-09-03 08:32 UTC + Fable mc10
    ratification, extended by Fable D7 mc00-2026-09-04):

    - `opening_wdv`     = value carried INTO the range (close of `from_date - 1`)
    - `cost_additions`  = TOTAL cost that entered the ledger INSIDE the
                          range window. Zero when acquisition falls
                          outside [from_date, to_date] (both endpoints
                          inclusive per RATIFIED §2 Ask 3); equals
                          asset.cost when acquisition falls inside.
                          Future extension will accumulate
                          `event_type=cost_addition` events on top.
    - `closing_wdv`     = value carried OUT of the range (close of `to_date`)
    - `range_dep`       = the charge between them.

    **Three-term identity (Fable D7 mc00-2026-09-04 replaces the earlier
    two-term):**

        closing_wdv == opening_wdv + cost_additions − range_dep

    Holds under `monthly` by construction (each month quantised then
    summed); under `actual/actual` and `actual/365` derived from anchors
    per Fable D2 mc15 fix. Two-term identity is a corollary when
    `cost_additions == 0` (acquisition-outside-range case; cells 3, 4, 6,
    11, 12b of Fable's post-matrix probe).

    Fable ruling verbatim (§4): *"`/range/` gains `cost_additions`,
    always present, and the three-term identity replaces the two-term
    one everywhere it is asserted. And extend the property test first.
    The 48-configuration matrix asserts the two-term identity, which
    means no configuration in it has a range spanning the acquisition
    date — a fixture that cannot fail on the case this endpoint was
    rewritten twice to handle. Add acquisition-inside-range
    configurations, watch them fail, then fix."*

    Gateway-side synthesis: if the engine's response omits
    `cost_additions`, the gateway derives it from algebraic rearrangement
    of the three-term identity:

        cost_additions = closing_wdv + range_dep − opening_wdv

    See `api.routes.calculators.invoke_depreciation_range` for the
    synthesis site. When the engine ships `cost_additions` in its own
    response (F13-UPHELD engine authority), the gateway passes it
    through verbatim without rewriting.
    """

    model_config = ConfigDict(extra="allow")  # engine may return extra fields

    basis: Annotated[
        GatewayBasisLiteral,
        Field(description="Echoed basis from request."),
    ]

    from_date: Annotated[
        date, Field(description="Echoed from_date from request.")
    ]

    to_date: Annotated[
        date, Field(description="Echoed to_date from request.")
    ]

    day_count: Annotated[
        DayCountLiteral,
        Field(
            description=(
                "Echoed day_count convention. Callers should verify the "
                "echoed value matches what they sent (defensive against "
                "silent-convention-substitution class defects)."
            ),
        ),
    ]

    days_in_range: Annotated[
        int,
        Field(
            description=(
                "(to_date - from_date).days + 1 (inclusive-both-endpoints). "
                "Explicit field per RATIFIED §2 Ask 3 so callers can "
                "byte-verify their inclusive-endpoints expectation."
            ),
        ),
    ]

    range_dep: Annotated[
        Decimal,
        Field(
            description=(
                "Total depreciation charge over [from_date, to_date] "
                "inclusive. Zero-day range (from_date == to_date) returns "
                "Decimal('0.00'). **Three-term ledger identity (Fable D7 "
                "mc00-2026-09-04):** `range_dep = opening_wdv + "
                "cost_additions − closing_wdv`. Rearrange this to "
                "reconcile any three of the four fields against the "
                "fourth. The two-term identity `range_dep = opening_wdv "
                "- closing_wdv` remains valid whenever `cost_additions "
                "== 0.00` (acquisition-outside-range case)."
            ),
        ),
    ]

    cost_additions: Annotated[
        Decimal,
        Field(
            default=Decimal("0.00"),
            description=(
                "Total cost that entered the ledger INSIDE the range "
                "window (inclusive of both endpoints). Zero when "
                "acquisition falls outside [from_date, to_date]; equals "
                "asset.cost when acquisition falls inside (the range "
                "spans the acquisition date). Future extension will "
                "accumulate `event_type=cost_addition` lifecycle events "
                "on top of the acquisition. Fable D7 mc00-2026-09-04 "
                "ratification: `always present`, and the three-term "
                "identity `closing_wdv = opening_wdv + cost_additions "
                "− range_dep` replaces the two-term one everywhere. "
                "Gateway synthesises this field from algebraic "
                "rearrangement when the engine's response omits it "
                "(engine may ship it directly in a later release; "
                "F13-UPHELD passthrough when it does)."
            ),
        ),
    ] = Decimal("0.00")

    opening_wdv: Annotated[
        Decimal,
        Field(
            description=(
                "Opening balance carried INTO the range — the value at "
                "close of `from_date - 1`. Ledger vocabulary (AASB 116 "
                "carrying amount). Renamed from `wdv_at_from_date` at "
                "Andrew ruling 2026-09-03 08:32 UTC. **Pre-acquisition "
                "case:** if `from_date < asset.acquisition_date`, "
                "`opening_wdv = 0.00` and `truncated` is `True`."
            ),
        ),
    ]

    closing_wdv: Annotated[
        Decimal,
        Field(
            description=(
                "Closing balance carried OUT of the range — the value at "
                "close of `to_date`. Ledger vocabulary. Renamed from "
                "`wdv_at_to_date` at Andrew ruling 2026-09-03 08:32 UTC. "
                "Invariant: `opening_wdv - range_dep == closing_wdv`."
            ),
        ),
    ]

    truncated: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "True when the requested range window was wider than the "
                "depreciation the engine could actually post. Fires under "
                "any of: (a) `from_date < acquisition_date`; (b) "
                "`opening_wdv > 0` and `closing_wdv == 0` (range extends "
                "past useful-life-end); (c) `opening_wdv == 0` and NOT "
                "pre-acquisition (asset was fully depreciated BEFORE the "
                "range started). Agents MUST check this field: "
                "`range_dep = 0.00` with `truncated = true` means the "
                "answer is zero because the asset had no value during the "
                "range, NOT because depreciation happens to be zero in "
                "that window."
            ),
        ),
    ] = False
