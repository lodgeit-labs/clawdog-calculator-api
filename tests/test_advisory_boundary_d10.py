"""Advisory-boundary D10: basis-conditioned framing.

**Fable D10 mc00-2026-09-04 ruling (Andrew-raised; corrects Fable's own
D6 ruling).**

Prior state (pre-mc00): every calculator response carried the tax-agent
statutory frame (TAA 1953 s284-15 + TASA 2009 + `registered_agent_
required: true`) including on accounting-basis computations. Andrew
surfaced this as wrong because:

  * TASA 2009 governs tax-agent services *for a fee*. Computing an
    accounting depreciation charge is not one.
  * `registered_agent_required: true` claims a legal requirement that
    does not exist for accounting figures.
  * TAA 1953 s284-15 penalises false statements *made to the
    Commissioner*. An accounting carrying amount does not enter a return.

Fable ruled (verbatim):

  "The advisory conditions on `basis` as well as on the manifest. Same
   mechanism, second discriminator, so FBT and Div7A keep the TAA/TASA
   framing where it is apt.
   ...
   The sentence that earns its place is the negative one. The real
   misuse risk is a tester carrying an accounting carrying amount
   into a tax return, where Div 40 rates and rules differ and the
   figure will be wrong. Nothing in the current response warns
   against that, and it is the one warning this endpoint actually
   needs."

Contract shipped:

  basis="accounting"  ->  disclaimer = ADVISORY_TEXT_AU_ACCOUNTING
                          statutory_basis = STATUTORY_BASIS_AU_ACCOUNTING
                                            (AASB 116 + AASB 108)
                          registered_agent_required = FALSE

  basis="tax" | other ->  incumbent advisory (TAA + TASA + True)

  basis absent (FBT / ->  incumbent advisory (backwards compatible)
       Div7A)

  Precedence: basis="accounting" wins over the D6 empty-manifest
              discriminator. The accounting text already carries both
              the no-rate-tables observation and the correct statutory
              frame.

Paragraph-number sourcing (Fable ruling: do NOT cite AASB paragraph
numbers from memory): AASB 116.51 (useful life + residual value review)
and AASB 116.61 (depreciation method review) sourced 2026-09-04 06:59
UTC via:
  1. https://standards.aasb.gov.au/aasb-116-dec-2022 (AASB compilation
     preamble confirming AASB 116 mirrors IAS 16 verbatim except Aus-
     prefixed paragraphs).
  2. https://cpcongroup.com/insights/article/ias-16-51-annual-useful-
     life-review/ (secondary source reproducing IAS 16.51 wording +
     naming both paragraph 51 and paragraph 61).

The advisory PARAPHRASES the requirement and CITES by paragraph. AASB
Standards material is copyright IFRS Foundation + Commonwealth of
Australia; verbatim quotation would need reproduction rights.
"""
from __future__ import annotations

from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.lib.advisory_boundary import (
    ADVISORY_TEXT_AU,
    ADVISORY_TEXT_AU_ACCOUNTING,
    ADVISORY_TEXT_AU_EMPTY_MANIFEST,
    advisory_block,
    wrap_response,
)
from api.main import app

DEP_AT_PERIOD = "urn:sbrm:period:depreciation:unscoped"


# ============================================================================
# Unit level (advisory_block helper)
# ============================================================================


def test_advisory_block_accounting_uses_aasb_disclaimer():
    block = advisory_block("AU", basis="accounting")
    assert block["disclaimer"] == ADVISORY_TEXT_AU_ACCOUNTING
    assert block["jurisdiction"] == "AU"
    assert block["registered_agent_required"] is False


def test_advisory_block_accounting_statutory_basis_replaces_taa_with_aasb():
    """Accounting-branch statutory_basis carries AASB references and does
    NOT carry TAA / TASA. Fable D10 ruling: TAA and TASA are inapplicable
    on this figure, so they must not appear in the statutory frame."""
    block = advisory_block("AU", basis="accounting")
    statutes = {(b["statute"], b["section"]) for b in block["statutory_basis"]}
    # Positive: AASB 116 + AASB 108 present
    assert any(s[0] == "AASB 116" for s in statutes), (
        f"Accounting branch must cite AASB 116; got {statutes}"
    )
    assert any(s[0] == "AASB 108" for s in statutes), (
        f"Accounting branch must cite AASB 108 (change in accounting "
        f"estimate framework); got {statutes}"
    )
    # Negative: TAA / TASA MUST NOT appear on the accounting branch
    assert not any(s[0] == "TAA 1953" for s in statutes), (
        f"Accounting branch must NOT cite TAA 1953 (Fable D10: "
        f"TAA s284-15 penalises statements to the Commissioner; an "
        f"accounting carrying amount does not enter a return); got {statutes}"
    )
    assert not any(s[0].startswith("Tax Agent Services") for s in statutes), (
        f"Accounting branch must NOT cite TASA (Fable D10: TASA governs "
        f"registered-agent services for a fee; accounting computation is "
        f"not one); got {statutes}"
    )


def test_advisory_block_accounting_disclaimer_carries_load_bearing_negative():
    """Fable D10 verbatim: 'The sentence that earns its place is the
    negative one. The real misuse risk is a tester carrying an accounting
    carrying amount into a tax return, where Div 40 rates and rules
    differ and the figure will be wrong.'"""
    block = advisory_block("AU", basis="accounting")
    disc = block["disclaimer"]
    assert "Do not carry this figure into a tax return" in disc, (
        f"Load-bearing negative sentence missing from accounting-branch "
        f"disclaimer. Fable ruled this is the one warning this endpoint "
        f"actually needs. Got: {disc[:400]!r}"
    )
    # And it must name Division 40 specifically (the tax framework a
    # tester might confuse this with).
    assert "Division 40" in disc or "Div 40" in disc, (
        f"Negative sentence must name ITAA 1997 Division 40 so the "
        f"tester knows which framework this figure is NOT under. "
        f"Got: {disc[:400]!r}"
    )


def test_advisory_block_accounting_disclaimer_cites_aasb_review_paragraphs():
    """AASB 116.51 (useful life + residual value) and AASB 116.61
    (depreciation method) sourced from public standards material 2026-09-04
    06:59 UTC; the disclaimer must carry both paragraph references so a
    caller can trace the review requirement to the standard."""
    block = advisory_block("AU", basis="accounting")
    disc = block["disclaimer"]
    assert "AASB 116" in disc, f"Must cite AASB 116 explicitly. Got: {disc[:400]!r}"
    assert "paragraph 51" in disc, (
        f"Must cite paragraph 51 (useful life + residual value review). "
        f"Got: {disc[:400]!r}"
    )
    assert "paragraph 61" in disc, (
        f"Must cite paragraph 61 (depreciation method review). "
        f"Got: {disc[:400]!r}"
    )
    assert "AASB 108" in disc, (
        f"Must cite AASB 108 (change-in-accounting-estimate framework). "
        f"Got: {disc[:400]!r}"
    )


def test_advisory_block_accounting_does_not_carry_taa_tasa_in_disclaimer():
    """Cross-check on the disclaimer text: TAA 1953 s284-15 and TASA 2009
    strings must not leak into the accounting-branch disclaimer either."""
    block = advisory_block("AU", basis="accounting")
    disc = block["disclaimer"]
    assert "TAA 1953" not in disc, (
        f"Accounting disclaimer must NOT mention TAA 1953. Got: {disc[:400]!r}"
    )
    assert "Tax Agent Services Act" not in disc, (
        f"Accounting disclaimer must NOT mention TASA. Got: {disc[:400]!r}"
    )
    assert "registered tax agent" not in disc.lower(), (
        f"Accounting disclaimer must NOT recommend consulting a registered "
        f"tax agent (Fable D10: TASA governs services for a fee; computing "
        f"an accounting figure is not one). Got: {disc[:400]!r}"
    )


# ============================================================================
# Discriminator interaction — basis wins over manifest emptiness
# ============================================================================


def test_advisory_block_accounting_beats_empty_manifest_discriminator():
    """When BOTH discriminators apply (basis=accounting + empty manifest,
    which is the state depreciation lives in), basis wins. The accounting
    text already covers 'no rate tables consumed' via 'derived
    arithmetically from the inputs supplied' framing."""
    block = advisory_block(
        "AU",
        manifest_rate_table_uris=[],  # would normally pick empty-manifest text
        basis="accounting",
    )
    assert block["disclaimer"] == ADVISORY_TEXT_AU_ACCOUNTING
    assert block["disclaimer"] != ADVISORY_TEXT_AU_EMPTY_MANIFEST


def test_advisory_block_tax_basis_retains_incumbent_framing():
    """Fable D10 explicitly preserves TAA/TASA on the tax branch."""
    block = advisory_block("AU", basis="tax")
    # Falls into the incumbent branch (no manifest supplied → default text)
    assert block["disclaimer"] == ADVISORY_TEXT_AU
    assert block["registered_agent_required"] is True
    statutes = {(b["statute"], b["section"]) for b in block["statutory_basis"]}
    assert ("TAA 1953", "s284-15") in statutes


def test_advisory_block_basis_absent_defaults_to_incumbent():
    """FBT and Div7A responses do not carry `basis` at the payload top
    level (their basis is implicit in the calculator identity). When basis
    is absent, the incumbent tax-agent framing applies — backwards
    compatible with FBT + Div7A."""
    block = advisory_block("AU", basis=None)
    assert block["disclaimer"] == ADVISORY_TEXT_AU
    assert block["registered_agent_required"] is True


# ============================================================================
# wrap_response routing — reads basis off the payload
# ============================================================================


def test_wrap_response_routes_by_payload_basis_accounting():
    """wrap_response reads payload['basis'] and routes correctly."""
    out = wrap_response(
        {
            "basis": "accounting",
            "wdv_at": "5000.00",
            "manifest": {"rate_table_uris": []},
        },
        jurisdiction="AU",
    )
    assert out["advisory"]["disclaimer"] == ADVISORY_TEXT_AU_ACCOUNTING
    assert out["advisory"]["registered_agent_required"] is False


def test_wrap_response_routes_by_payload_basis_tax():
    out = wrap_response(
        {"basis": "tax", "wdv_at": "5000.00", "manifest": {"rate_table_uris": []}},
        jurisdiction="AU",
    )
    # tax basis + empty manifest -> empty-manifest text (D6 discriminator applies)
    assert out["advisory"]["disclaimer"] == ADVISORY_TEXT_AU_EMPTY_MANIFEST
    assert out["advisory"]["registered_agent_required"] is True


def test_wrap_response_no_basis_backwards_compatible():
    """FBT-shaped payload with no basis field keeps historic advisory."""
    out = wrap_response(
        {"taxable_value": 100.0, "manifest": {"rate_table_uris": [{"uri": "urn:x"}]}},
        jurisdiction="AU",
    )
    assert out["advisory"]["disclaimer"] == ADVISORY_TEXT_AU
    assert out["advisory"]["registered_agent_required"] is True


# ============================================================================
# End-to-end route — accounting-basis depreciation returns D10 advisory
# ============================================================================


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_depreciation_at_accounting_payload_returns_d10_advisory(
    client: TestClient,
) -> None:
    """The end-to-end assertion. A well-formed accounting-basis depreciation
    request must return an advisory block whose disclaimer names AASB 116,
    whose statutory_basis carries AASB 116 + AASB 108, whose registered_
    agent_required is FALSE, and which does not mention TAA / TASA anywhere."""
    from unittest.mock import AsyncMock, patch

    canonical_response = {
        "basis": "accounting",
        "at_date": "2025-06-30",
        "wdv_at": "3500.00",
        "period_dep_at": "500.00",
        "day_count": "actual/actual",
    }
    with patch(
        "api.routes.calculators.PrologClient.depreciation_at",
        new_callable=AsyncMock,
        return_value=canonical_response,
    ):
        resp = client.post(
            f"/v1/calculators/depreciation/at/{quote(DEP_AT_PERIOD, safe='')}",
            json={
                "basis": "accounting",
                "asset": {
                    "cost": "5000.00",
                    "acquisition_date": "2022-07-01",
                    "accounting_useful_life_years": 10,
                    "accounting_method": "prime_cost",
                },
                "at_date": "2025-06-30",
                "events": [],
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    advisory = body["advisory"]

    # Structural: registered_agent_required flipped.
    assert advisory["registered_agent_required"] is False

    # Statutory_basis: AASB present, TAA/TASA absent.
    statutes = {(b["statute"], b["section"]) for b in advisory["statutory_basis"]}
    assert any(s[0] == "AASB 116" for s in statutes)
    assert any(s[0] == "AASB 108" for s in statutes)
    assert not any(s[0] == "TAA 1953" for s in statutes)
    assert not any(s[0].startswith("Tax Agent Services") for s in statutes)

    # Disclaimer content.
    disc = advisory["disclaimer"]
    assert "AASB 116" in disc
    assert "Do not carry this figure into a tax return" in disc
    assert "TAA 1953" not in disc
    assert "Tax Agent Services Act" not in disc
