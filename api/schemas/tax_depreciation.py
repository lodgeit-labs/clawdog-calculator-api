"""Tax-depreciation calculator input schemas for the constellation gateway.

Covers the three AU *tax* depreciation calculators onboarded at the dispatch
route ``POST /v1/calculators/tax-depreciation/{calculator}/{period_uri}``,
where ``{calculator}`` is one of ``decline-in-value`` | ``low-value-pool`` |
``small-business-pool`` (SCOPE_tax_depreciation_v1.md §3, §4).

**Two-depreciations discipline (§2).** This is AU *tax* depreciation — the
decline-in-value deduction under ITAA 1997 Division 40 and the pooling rules
under Subdivision 328-D. It is a statutory income-tax deduction and is distinct
from the accounting depreciation (AASB 116 carrying amount) exposed by the
separate ``depreciation`` module. The two are not interchangeable.

**Money as decimal strings, cent-checked by the gateway (§5, §10).** Unlike the
older FBT/depreciation engines (which receive floats), this engine follows the
hp pattern: money crosses the wire as decimal strings and no float ever touches
the arithmetic. Every money field below is a ``str`` validated by the gateway to
be whole cents via :func:`reject_sub_cent_string`; a sub-cent / non-numeric
value is rejected with a 422 ``money_not_cent_quantised`` before the engine is
called. Dates are ``YYYY-MM-DD``; percentages and lives are JSON numbers.

**Life is an input, never looked up (§2, §4).** ``effective_life_years`` is a
required field on ``decline-in-value`` with no ``asset_description`` fallback —
effective-life lookup is out of scope for these calculators (that is the rate
finder's job).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.schemas.money import reject_sub_cent_string


def _money_field(description: str, *, optional: bool = False):
    """A money field declared as a decimal string with the x-money marker.

    Mirrors the hp-schedule pattern (``api/schemas/hp.py``): the field is a
    ``str`` on the wire, carries ``x-money: true`` in the OpenAPI schema, and
    is cent-scale-checked by a field validator on the owning model.
    """
    return Field(
        default=None if optional else ...,
        description=(
            description + " Money: cent-quantised decimal string."
        ),
        json_schema_extra={"x-money": True},
    )


class TaxDepSecondElementCost(BaseModel):
    """A second-element cost incurred during the income year (§4.1, §4.2)."""

    # extra="forbid": an unknown nested field is a 422, not silently dropped —
    # so a typo (e.g. effective_life for effective_life_years) is named, not
    # ignored. Applies to nested models too (Fable [CALC] 2026-10-22).
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    date: str = Field(description="Date the cost was incurred, ISO (YYYY-MM-DD).")
    amount: str = _money_field("Second-element cost amount.")

    @field_validator("amount", mode="after")
    @classmethod
    def _amount_cent_scale(cls, v: str) -> str:
        return reject_sub_cent_string(v)


class TaxDepDisposal(BaseModel):
    """A disposal in the income year (§4.1, s 40-285)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    date: str = Field(description="Disposal date, ISO (YYYY-MM-DD).")
    termination_value: str = _money_field("Termination (disposal) value.")

    @field_validator("termination_value", mode="after")
    @classmethod
    def _tv_cent_scale(cls, v: str) -> str:
        return reject_sub_cent_string(v)


class DeclineInValueInput(BaseModel):
    """``decline-in-value`` — one asset, one year (ITAA 1997 s 40-70 DV,
    s 40-75 prime cost). SCOPE §4.1.

    ``effective_life_years`` is REQUIRED with no ``asset_description`` fallback
    (§2, §4): effective-life lookup is out of scope.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        # extra="forbid": reject unknown fields with a 422 naming the offending
        # key, so a typo like effective_life (for effective_life_years) or an
        # out-of-scope asset_description fallback is surfaced, not swallowed.
        extra="forbid",
        json_schema_extra={
            "x-calc-uri": "urn:sbrm:calculator:tax-depreciation:decline-in-value"
        },
    )

    method: Literal["diminishing_value", "prime_cost"] = Field(
        description="Decline-in-value method: diminishing_value | prime_cost."
    )
    cost: str = _money_field("First element of cost.")
    start_held_date: str = Field(
        description="Date the asset started to be held for use (YYYY-MM-DD)."
    )
    effective_life_years: float = Field(
        gt=0,
        description=(
            "Effective life in years (> 0). REQUIRED input; no asset-description "
            "fallback — effective-life lookup is out of scope for this "
            "calculator (§2, §4.1). DV rate = 200% / life for assets first held "
            "after 9 May 2006; 150% / life before."
        ),
    )
    opening_adjustable_value: str = _money_field(
        "Opening adjustable value; omit in the year of acquisition.",
        optional=True,
    )
    second_element_costs: list[TaxDepSecondElementCost] | None = Field(
        default=None,
        description="Second-element costs incurred during the year.",
    )
    taxable_use_percent: float = Field(
        default=100.0,
        ge=0,
        le=100,
        description="Taxable-use percentage 0–100 (default 100).",
    )
    is_car: bool = Field(
        default=False,
        description=(
            "True to apply the car cost limit (s 40-230) from the year's rate "
            "table."
        ),
    )
    disposal: TaxDepDisposal | None = Field(
        default=None, description="Disposal in the year, if any."
    )

    @field_validator("cost", "opening_adjustable_value", mode="after")
    @classmethod
    def _money_cent_scale(cls, v: str | None) -> str | None:
        return None if v is None else reject_sub_cent_string(v)


class LowValuePoolInput(BaseModel):
    """``low-value-pool`` — one pool, one year (ITAA 1997 s 40-440). SCOPE §4.2."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        json_schema_extra={
            "x-calc-uri": "urn:sbrm:calculator:tax-depreciation:low-value-pool"
        },
    )

    opening_pool_balance: str = _money_field("Opening pool balance (A).")
    opening_adjustable_value_of_assets_allocated: str = _money_field(
        "Opening adjustable value of assets allocated this year (B).",
        optional=True,
    )
    cost_of_low_cost_assets_allocated: str = _money_field(
        "Cost of low-cost assets allocated this year, taxable-use reduced (C).",
        optional=True,
    )
    second_element_costs: str = _money_field(
        "Second-element costs added during the year (D).",
        optional=True,
    )
    reduced_termination_values: str = _money_field(
        "Reduced termination values of assets disposed from the pool.",
        optional=True,
    )

    @field_validator(
        "opening_pool_balance",
        "opening_adjustable_value_of_assets_allocated",
        "cost_of_low_cost_assets_allocated",
        "second_element_costs",
        "reduced_termination_values",
        mode="after",
    )
    @classmethod
    def _money_cent_scale(cls, v: str | None) -> str | None:
        return None if v is None else reject_sub_cent_string(v)


class SmallBusinessPoolInput(BaseModel):
    """``small-business-pool`` — one pool, one year (Subdiv 328-D). SCOPE §4.3."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        json_schema_extra={
            "x-calc-uri": "urn:sbrm:calculator:tax-depreciation:small-business-pool"
        },
    )

    opening_pool_balance: str = _money_field("Opening pool balance.")
    additions: str = _money_field(
        "Additions during the year, taxable-use reduced.",
        optional=True,
    )
    reductions: str = _money_field(
        "Reductions / termination values from the pool.",
        optional=True,
    )
    instant_asset_write_off_items: str = _money_field(
        "Instant-asset-write-off items for the year.",
        optional=True,
    )

    @field_validator(
        "opening_pool_balance",
        "additions",
        "reductions",
        "instant_asset_write_off_items",
        mode="after",
    )
    @classmethod
    def _money_cent_scale(cls, v: str | None) -> str | None:
        return None if v is None else reject_sub_cent_string(v)


# Discriminated by the {calculator} path segment at the route layer. The route
# selects the right member before validation; OpenAPI advertises all three.
TaxDepreciationInput = (
    DeclineInValueInput | LowValuePoolInput | SmallBusinessPoolInput
)

# Map the engine {calculator} path segment to its gateway input model. The
# route validates the raw body against the member for the requested calculator,
# so each calculator's own field contract (money-as-string, cent-check, and the
# required effective_life_years with no fallback) is enforced gateway-side.
TAX_DEP_INPUT_MODEL_BY_SEGMENT: dict[str, type[BaseModel]] = {
    "decline-in-value": DeclineInValueInput,
    "low-value-pool": LowValuePoolInput,
    "small-business-pool": SmallBusinessPoolInput,
}

__all__ = [
    "DeclineInValueInput",
    "LowValuePoolInput",
    "SmallBusinessPoolInput",
    "TaxDepSecondElementCost",
    "TaxDepDisposal",
    "TaxDepreciationInput",
    "TAX_DEP_INPUT_MODEL_BY_SEGMENT",
]
