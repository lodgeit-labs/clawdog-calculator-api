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

from pydantic import BaseModel, ConfigDict, Field

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
