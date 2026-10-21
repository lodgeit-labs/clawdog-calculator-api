"""Tax-depreciation calculator input schema for the constellation gateway.

Mirrors the request shape accepted by the tax-depreciation-engine's dispatch
route ``POST /v1/calculators/tax-depreciation/{calculator}/{period_uri}``,
where ``{calculator}`` is one of ``decline-in-value`` | ``low-value-pool`` |
``small-business-pool``. The gateway forwards the payload verbatim to the
tax-depreciation-engine Cloud Run service via the shared dispatch transport.

**Two-depreciations discipline.** This is AU *tax* depreciation — the
decline-in-value deduction under ITAA 1997 Division 40 and the pooling rules
under Subdivision 328-D. It is a statutory tax figure and is distinct from the
accounting depreciation (AASB 116 carrying amount) exposed by the separate
``depreciation`` module. The two are not interchangeable; a tax-depreciation
figure is a deduction in an income tax return, an accounting-depreciation
figure is a carrying-amount movement in the financial statements.

**Verbatim-forward posture.** The engine owns the per-calculator field
contract (which fields each of the three calculators requires and their
bounds). The gateway does not duplicate that per-field validation; it forwards
the caller's body verbatim and surfaces the engine's typed 422 / 400 refusals
through the central error mapper. ``extra="allow"`` keeps the schema open so a
caller can send any field the engine accepts without the gateway rejecting it
ahead of the authoritative engine-side check.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TaxDepreciationInput(BaseModel):
    """Request body for the gateway's tax-depreciation dispatch route.

    Wire-shape mirrors the upstream tax-depreciation-engine dispatch endpoint.
    The selected ``{calculator}`` (decline-in-value | low-value-pool |
    small-business-pool) is carried in the URL path, not the body. The body is
    forwarded verbatim; the engine is the authoritative validator of each
    calculator's own field contract.

    Jurisdiction AU; statute ITAA 1997 Division 40 (decline in value) and
    Subdivision 328-D (small-business and low-value pooling). Election group
    tax-depreciation (no statutory default); see GET /v1/modules.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        # Verbatim-forward posture: the engine owns the per-calculator field
        # contract. The gateway does not reject fields the engine may accept.
        extra="allow",
        json_schema_extra={"x-calc-uri-prefix": "urn:sbrm:calculator:tax-depreciation"},
    )
