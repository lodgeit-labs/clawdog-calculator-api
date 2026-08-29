"""Div 7A calculator input schema for the constellation gateway.

Mirrors the request shape accepted by Div7A_Engine's FastAPI at
``POST /v1/calculators/div7a/at/{period_uri}``. The gateway forwards this
payload verbatim to the Div7A_Engine Cloud Run service via PrologClient.dispatch.

Phase D (mut-2026-08-24-mc20). Statute anchor: ITAA 1936 §§109D/109E/109N.
Canon 610 §1.1 MYR formula + §1.2 first-year gotcha (n_remaining = term - 1
in first real MYR year); canon 620 periodic-repayment daily-balance accrual.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Div7aRepaymentIn(BaseModel):
    """A single repayment event."""

    model_config = ConfigDict(populate_by_name=True)

    amount: float = Field(..., description="Repayment amount (AUD)")
    date: str = Field(
        ...,
        description="Repayment date (ISO YYYY-MM-DD or AU dd/mm/yyyy)",
    )
    loan_id: str | None = Field(
        default="default", description="Loan identifier"
    )
    allocation_hint: str | None = Field(
        default="unallocated",
        description="interest_first | principal_first | unallocated",
    )


class Div7aAtInput(BaseModel):
    """Div 7A single-income-year MYR request payload.

    Canonical URN: ``urn:sbrm:calculator:div7a:at`` per constellation naming
    convention (matches ``urn:sbrm:calculator:depreciation:at`` + ``urn:sbrm:calculator:fbt:*``).

    Field discipline:
      - ``amalgamated_base``: §109E amalgamated loan base amount at start of year (AUD)
      - ``loan_term_years``: §109N complying-loan term (7 unsecured / 25 secured)
      - ``loan_origination_date``: date the loan was made (ISO or dd/mm/yyyy)
      - ``income_year_start_date``: 1 July of the FY to compute (ISO or dd/mm/yyyy)
      - ``is_first_real_myr_year``: optional; derived from origination/year if omitted
      - ``repayments``: list; may be empty (canon 620 §1.1 single-annual or multi)
    """

    model_config = ConfigDict(populate_by_name=True)

    amalgamated_base: float = Field(
        ...,
        description="§109E amalgamated loan base amount (AUD)",
    )
    loan_term_years: int = Field(
        ...,
        description="§109N loan term in years (7 unsecured / 25 secured)",
    )
    loan_origination_date: str = Field(
        ...,
        description="Loan origination date (ISO YYYY-MM-DD or AU dd/mm/yyyy)",
    )
    income_year_start_date: str = Field(
        ...,
        description=(
            "Start of the income year to compute (ISO YYYY-MM-DD or AU "
            "dd/mm/yyyy). AU income year: 1 July – 30 June."
        ),
    )
    is_first_real_myr_year: bool | None = Field(
        default=None,
        description=(
            "Override for canon 610 §1.2 first-year gotcha. If omitted, "
            "engine derives from origination_date vs income_year_start_date."
        ),
    )
    repayments: list[Div7aRepaymentIn] = Field(
        default_factory=list,
        description="Repayment events; canon 620 daily-balance aggregation",
    )
