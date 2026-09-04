"""D11 discipline: no advisory branch mentions inputs the calculator
does not accept.

**Fable ruling mc01-2026-09-04 08:45 UTC (verbatim):**

  "The empty-manifest advisory is depreciation vocabulary, and it is
   now on FBT. FBT LAFHA's response carries:
     '…every figure is derived arithmetically from the inputs supplied
      in the request, under the day-count convention stated in this
      response. Whether those inputs — including the useful life, the
      method and the day-count convention — are appropriate…'
   FBT has no useful life, no depreciation method, and no day_count
   field anywhere in its response. The branch fires because FBT's
   rate_table_uris is also empty — the discriminator is manifest-
   emptiness, and I wrote text that assumed manifest-emptiness meant
   depreciation."

  "Add a test that fires every registered calculator through the
   advisory selector and asserts no branch mentions an input the
   calculator does not accept — that is the check that would have
   caught this, and it is the same class as the response-level
   assertion covenant you just banked."

Two shapes of assertion in this file:

  1. The empty-manifest branch's disclaimer is input-agnostic — it
     does not enumerate ANY specific input names. Whatever those
     inputs are (useful life, weeks lived away, loan term, base
     value), the sentence stays true. This is the D11 anchor: the
     shared branch text describes a shared property, not a specific
     family.

  2. Per-registered-calculator: fire the advisory selector with the
     shape that calculator's response would carry (empty manifest,
     no `basis`, or basis="accounting"), extract the disclaimer,
     and assert the disclaimer does not name terms specific to
     OTHER calculator families that this calculator does not accept.
"""
from __future__ import annotations

from api.lib.advisory_boundary import (
    ADVISORY_TEXT_AU,
    ADVISORY_TEXT_AU_ACCOUNTING,
    ADVISORY_TEXT_AU_EMPTY_MANIFEST,
    advisory_block,
)

# ============================================================================
# Direct assertion on the shared branch text
# ============================================================================


# Input-name terms that appear in one or more calculator families' input
# schemas but NOT in others. The empty-manifest branch is fired by MULTIPLE
# families (depreciation on /at/ + /range/ at v1; FBT calcs whose fold
# doesn't touch a rate table like LAFHA + property + expense-payment; Div7A
# only when its manifest is empty which today it isn't). So the branch's
# text MUST NOT name any of these terms — a caller reading the disclaimer
# on LAFHA output must not see depreciation terminology, and vice versa.
#
# Kept as a plain list rather than pulling from the schema classes so the
# test's own vocabulary is legible + auditable at a glance. Extend as new
# calculator families ship.
_INPUT_NAME_TERMS = [
    # Depreciation vocabulary
    "useful life",
    "useful_life",
    "depreciation method",
    "day-count",
    "day_count",
    "prime cost",
    "diminishing value",
    "acquisition date",
    # FBT vocabulary
    "weeks lived away",
    "weeksLivedAway",
    "accommodation per week",
    "meals per week",
    "employee contribution",
    "business use percentage",
    "acquisition cost",
    "statutory fraction",
    # Div7A vocabulary
    "amalgamated base",
    "amalgamated_base",
    "loan term",
    "loan_term_years",
    "loan origination",
    "benchmark rate",
    "repayment",
]


def test_empty_manifest_disclaimer_is_input_agnostic():
    """D11 mc01-2026-09-04 08:45 UTC anchor: the empty-manifest branch
    text (which fires across depreciation + FBT-LAFHA-shape calcs + any
    future calc whose fold doesn't consume rate-tables) MUST NOT name
    inputs specific to any one calculator family."""
    disc = ADVISORY_TEXT_AU_EMPTY_MANIFEST
    disc_lower = disc.lower()
    for term in _INPUT_NAME_TERMS:
        assert term.lower() not in disc_lower, (
            f"Empty-manifest disclaimer names {term!r} \u2014 an input "
            f"specific to a calculator family that this shared branch "
            f"also serves. Fable D11 mc01-2026-09-04 08:45 UTC discipline: "
            f"the empty-manifest branch text is input-agnostic.\n"
            f"Disclaimer: {disc}"
        )


def test_empty_manifest_disclaimer_names_the_shared_property():
    \
        """Positive counter-assertion: the empty-manifest disclaimer DOES
    name the shared property (no rate tables consumed + inputs supplied
    in the request + not-assessed caveat). That is what earns its place
    in the shared branch, per Fable's D10 ruling on load-bearing negative
    sentences applied to D11's shared-branch shape."""
    disc = ADVISORY_TEXT_AU_EMPTY_MANIFEST
    assert "consumes no statutory rate tables" in disc, (
        f"Empty-manifest branch must state the load-bearing property. "
        f"Got: {disc}"
    )
    assert "inputs supplied in this request" in disc, (
        f"Empty-manifest branch must say WHERE the figure comes from "
        f"(inputs supplied). Got: {disc}"
    )
    assert "not assessed by this calculator" in disc, (
        f"Empty-manifest branch must carry the not-assessed caveat. "
        f"Got: {disc}"
    )


def test_incumbent_advisory_disclaimer_is_input_agnostic():
    \
        """Same discipline applied to the non-empty-manifest branch. It
    fires on FBT + Div7A wherever the manifest cites rate tables. The
    text there should also not enumerate inputs from OTHER families."""
    disc = ADVISORY_TEXT_AU
    disc_lower = disc.lower()
    for term in _INPUT_NAME_TERMS:
        assert term.lower() not in disc_lower, (
            f"Incumbent advisory disclaimer names {term!r} \u2014 an input "
            f"specific to a calculator family that this shared branch "
            f"also serves. Got: {disc}"
        )


def test_accounting_basis_advisory_may_name_accounting_inputs():
    \
        """Fable D10 ruling: the accounting-basis branch legitimately names
    accounting inputs (useful life, method, residual value) because it
    fires ONLY on accounting-basis payloads. Not a shared branch; the
    D11 discipline does not apply here.

    This test is the positive corollary of the D11 discipline: it pins
    the shape difference so a future reader is not confused by seeing
    'useful life' in one branch and asserting it's a defect.\"\"\"\n"""
    disc = ADVISORY_TEXT_AU_ACCOUNTING
    # Accounting branch is ALLOWED to name accounting inputs \u2014 they
    # are what this branch is about.
    assert "useful life" in disc.lower(), (
        f"Accounting-basis branch SHOULD name useful life (D10 body). "
        f"If this fails, D10 has regressed; not D11.\n"
        f"Disclaimer: {disc}"
    )


# ============================================================================
# Fire the advisory selector through the shapes each calculator produces
# ============================================================================


def test_advisory_selector_for_fbt_lafha_shape_stays_input_agnostic():
    """D11 anchor case: FBT LAFHA fires the empty-manifest branch
    (its manifest.rate_table_uris is []; its response has no `basis`
    field). The selected disclaimer MUST NOT name depreciation
    vocabulary."""
    block = advisory_block(
        "AU", manifest_rate_table_uris=[], basis=None
    )
    disc = block["disclaimer"]
    assert disc == ADVISORY_TEXT_AU_EMPTY_MANIFEST
    # Regression-guard the specific defect Fable named:
    for depreciation_term in [
        "useful life", "day-count", "day_count", "prime cost",
        "diminishing value",
    ]:
        assert depreciation_term not in disc.lower(), (
            f"FBT LAFHA advisory selected the empty-manifest branch and "
            f"the branch mentioned {depreciation_term!r} \u2014 depreciation "
            f"vocabulary that LAFHA does not accept. D11 defect.\n"
            f"Disclaimer: {disc}"
        )


def test_advisory_selector_for_depreciation_at_shape_stays_input_agnostic():
    """Depreciation /at/ empty manifest with accounting basis -> D10
    accounting-basis branch takes precedence. Fires the ACCOUNTING
    disclaimer, which legitimately names useful life. NOT a D11 case."""
    block = advisory_block(
        "AU", manifest_rate_table_uris=[], basis="accounting"
    )
    disc = block["disclaimer"]
    assert disc == ADVISORY_TEXT_AU_ACCOUNTING
    # useful life IS allowed here (D10 body).


def test_advisory_selector_for_div7a_shape_stays_input_agnostic():
    """Div7A response carries a non-empty manifest (canon 620 benchmark
    rate consumed). Fires the incumbent-non-empty branch. That branch
    is shared with FBT non-empty-manifest calcs so the same input-
    agnostic discipline applies."""
    block = advisory_block(
        "AU",
        manifest_rate_table_uris=[
            {"uri": "urn:sbrm:rate:div7a:fy2025:benchmark-interest"}
        ],
        basis=None,
    )
    disc = block["disclaimer"]
    assert disc == ADVISORY_TEXT_AU
    for foreign_term in [
        "useful life", "day-count", "weeks lived away", "amalgamated base",
    ]:
        assert foreign_term.lower() not in disc.lower(), (
            f"Div7A hit the incumbent advisory branch and it mentioned "
            f"{foreign_term!r} \u2014 an input specific to a different "
            f"calculator family. Shared branch defect.\n"
            f"Disclaimer: {disc}"
        )
