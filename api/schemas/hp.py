"""Pydantic input/output models for the hire purchase schedule calculator.

Money values cross the wire as decimal strings so no float ever touches the
amortisation. The engine (``api.engines.hp.schedule``) is the executable
specification; these models only shape the request/response contract.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HpBalloonInput(BaseModel):
    """A balloon payment on a specific instalment row.

    ``mode`` is required whenever a balloon is present; there is no default.
    """

    amount: str = Field(description="Balloon amount as a decimal string.")
    instalment_number: int = Field(
        ge=1, description="1-based instalment row the balloon lands on."
    )
    mode: Literal["replace", "add"] = Field(
        description=(
            "replace: the balloon replaces the regular instalment on its row. "
            "add: the balloon is paid in addition to the regular instalment on "
            "its row. Required; no default."
        )
    )


class HpScheduleInput(BaseModel):
    """Input contract for urn:sbrm:calculator:hp:schedule."""

    amount_financed: str = Field(description="Amount financed as a decimal string.")
    annual_rate_pct: str = Field(
        description="Nominal annual interest rate percentage as a decimal string."
    )
    term_regular_instalments: int = Field(
        ge=1, description="Number of regular instalments (excludes any balloon row)."
    )
    instalment: str = Field(description="Regular instalment amount as a decimal string.")
    timing: Literal["in_arrears", "in_advance"] = Field(
        description="Payment timing within each period."
    )
    frequency: str = Field(
        description="Instalment frequency. v1 supports 'monthly' only."
    )
    begin_date: str = Field(description="Contract start date, ISO (YYYY-MM-DD).")
    contract_form: Literal[
        "hire_purchase", "chattel_mortgage", "equipment_loan"
    ] = Field(
        description=(
            "Legal form. Affects GST and title treatment, not the amortisation. "
            "Required."
        )
    )
    balloon: HpBalloonInput | None = Field(
        default=None, description="Optional balloon payment."
    )
    fy_end_month: int = Field(
        default=6, ge=1, le=12, description="Financial-year end month (default June)."
    )


class HpScheduleRow(BaseModel):
    """One amortisation row; money fields are decimal strings."""

    instalment: int
    period_start: str
    period_end: str
    payment_date: str
    opening: str
    interest: str
    payment: str
    closing: str


class HpTotals(BaseModel):
    interest: str
    payments: str


class HpManifest(BaseModel):
    calculator: str
    engine_version: str
    accrual_basis: str


class HpAdvisory(BaseModel):
    figure_type: str
    notes: list[str]


class HpScheduleResponse(BaseModel):
    """Output contract for urn:sbrm:calculator:hp:schedule."""

    rows: list[HpScheduleRow]
    totals: HpTotals
    final_balance: str
    rate_precision_residual: str
    fy_interest: dict[str, str]
    fy_position: dict[str, dict[str, str]]
    manifest: HpManifest
    advisory: HpAdvisory
