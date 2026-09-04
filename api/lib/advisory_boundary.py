"""Advisory-boundary wrapper.

Implements CLAWDOG/110 §3.2 Non-Negotiable #2 (Advisory-Boundary Contract). Every
calculator-invocation response on every surface MUST carry an ``advisory`` block
citing the relevant statutory framing for the jurisdiction of the calculator.

The literal canonical disclaimer language for AU is supplied here; UK is included
as a forward-looking placeholder. The strings are paraphrases that **cite by
section** (TAA 1953 s284-15, Tax Agent Services Act 2009, Finance Act 2008
Sch41, AASB 116 paragraphs 51 + 61) — they are NOT verbatim transcriptions of
statute, which keeps Standing Rule #11 (Verbatim-Claim Byte-Diff Discipline)
clean: no sidecar required.

Lesson #34 anchor — the discipline is to surface the advisory-boundary concern
explicitly at every egress, not to retrofit it after first contact with auditors.
The check is binary: presence or absence on every endpoint that returns
calculator output.

**Fable D10 mc00-2026-09-04 amendment** (Andrew-raised; corrects Fable's own
D6 ruling). Prior state: every response carried a tax-legal frame (TAA 1953
s284-15 + TASA + `registered_agent_required: true`), including on
accounting-basis computations that produce an AASB 116 carrying amount which
does not enter a return. That framing was wrong on the accounting branch:
  * TASA 2009 governs registered tax-agent services *for a fee*. Computing
    an accounting depreciation charge is not one.
  * `registered_agent_required: true` asserts a legal requirement that does
    not exist for accounting figures.
  * TAA 1953 s284-15 penalises false statements *made to the Commissioner*.
    An accounting carrying amount does not enter a return.

D10 landed a second discriminator on the advisory: basis, alongside the D6
manifest-conditional discriminator. Same mechanism (payload-conditioning);
FBT and Div7A retain the TAA/TASA framing where it is apt (both compute
figures that enter returns).

Accounting-basis branch:
  * Cites AASB 116 as the standard the carrying amount is computed under.
  * Cites AASB 108 (via AASB 116.51 + AASB 116.61) as the standard governing
    the annual review of the caller-supplied useful life / depreciation
    method / residual value — the judgements this calculator does NOT assess.
  * Drops TAA 1953 s284-15 + TASA 2009 from `statutory_basis`.
  * Sets `registered_agent_required: false`.
  * Carries the load-bearing NEGATIVE sentence Fable ruled belonged here:
    warning against carrying an accounting carrying amount into a tax
    return, where ITAA 1997 Division 40 rates and rules differ and the
    figure will be wrong. This is the misuse risk the endpoint actually has.

Paragraph-number sourcing (Fable ruling: do not cite AASB paragraph numbers
from memory):
  * AASB 116.51 — residual value + useful life reviewed at least at each
    financial year-end; changes treated prospectively under AASB 108 as a
    change in accounting estimate.
  * AASB 116.61 — depreciation method reviewed at least at each financial
    year-end; changes treated prospectively under AASB 108.

Sourced 2026-09-04 06:59 UTC via Web Fetch of the AASB compilation preamble
(https://standards.aasb.gov.au/aasb-116-dec-2022 — confirms AASB 116 mirrors
IAS 16 verbatim except Aus‑prefixed paragraphs) and IAS 16.51 secondary
source https://cpcongroup.com/insights/article/ias-16-51-annual-useful-life-
review/ which reproduces the wording. Corroborated against IFRS official
copy at https://www.ifrs.org/content/dam/ifrs/publications/html-standards/
english/2025/issued/ias16.html which was fetched but paragraph 51 fell in
the truncated portion — the compilation preamble anchor is the load-bearing
citation for AASB‑to‑IAS parity.

Why not verbatim quote AASB paragraphs? Because AASB Standards material is
copyright IFRS Foundation + Commonwealth of Australia and reproduction rules
limit quotation. The disclaimer PARAPHRASES the requirement and CITES by
paragraph number; that keeps SR #11 clean.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Canonical advisory text — paraphrase + statutory citation by section. The
# wording is canonical to one byte; future iterations require a fresh helm-roll
# on CLAWDOG/109 §6 / CLAWDOG/110 §3.2 and a coordinated deployment.
#
# **Fable D6 mc21 2026-09-04 amendment:** the advisory is now conditioned on
# `manifest.rate_table_uris` (basis-independent condition; matches the reality
# of the emitted manifest, not calculator identity). Two branches:
#
#   * NON-EMPTY (rate tables consumed): `ADVISORY_TEXT_AU` (unchanged) states
#     "period-scoped statutory rate-tables cited in the manifest block" —
#     which is true when the manifest cites tables.
#
#   * EMPTY (no rate tables consumed — e.g. depreciation /at/ and /range/
#     at v1): `ADVISORY_TEXT_AU_EMPTY_MANIFEST` states what the output
#     actually rests on: "every figure is derived arithmetically from the
#     inputs supplied in the request, under the day-count convention stated
#     in this response" + the missing not-assessed caveat Fable ruled
#     load-bearing for the tester share: "Whether those inputs — including
#     the useful life, the method and the day-count convention — are
#     appropriate under the applicable accounting or tax framework is not
#     assessed by this calculator."
#
# TAA s284-15 + TASA framing is preserved in both branches (Fable ruled it
# correct + unrelated).
ADVISORY_TEXT_AU: str = (
    "This is calculator output, not advice. Consult a registered tax agent "
    "before relying on these numbers for any return, position, or advice "
    "provided to a third party. Calculator outputs reflect the period-scoped "
    "statutory rate-tables cited in the manifest block; statute may have "
    "changed since the rate-table was last anchored. "
    "Statutory framing: TAA 1953 s284-15 (false or misleading statements; "
    "penalty bands escalate with culpability) and the Tax Agent Services "
    "Act 2009 (registered-agent requirement)."
)

ADVISORY_TEXT_AU_EMPTY_MANIFEST: str = (
    "This is calculator output, not advice. Consult a registered tax agent "
    "before relying on these numbers for any return, position, or advice "
    "provided to a third party. This calculation consumes no statutory "
    "rate tables; every figure is derived arithmetically from the inputs "
    "supplied in the request, under the day-count convention stated in "
    "this response. Whether those inputs — including the useful life, the "
    "method and the day-count convention — are appropriate under the "
    "applicable accounting or tax framework is not assessed by this "
    "calculator. "
    "Statutory framing: TAA 1953 s284-15 (false or misleading statements; "
    "penalty bands escalate with culpability) and the Tax Agent Services "
    "Act 2009 (registered-agent requirement)."
)

# Fable D10 mc00-2026-09-04 accounting-basis text. This is what a caller on
# basis="accounting" sees. Two structural differences from the incumbent /
# empty-manifest text:
#
#   1. Positive statement of what the output IS: an AASB 116 carrying amount.
#   2. Load-bearing NEGATIVE statement of what the output MUST NOT be used
#      for: carrying into a tax return, where ITAA 1997 Div 40 rates + rules
#      differ + the figure will be wrong. Fable ruled this the one warning
#      this endpoint actually needs.
#
# The paragraph references (AASB 116.51, AASB 116.61) are what govern the
# annual review of the CALLER-SUPPLIED inputs (useful life, residual value,
# depreciation method) — the judgements this calculator does NOT assess.
# Fable ruled that the sentence naming what is NOT assessed is what earns
# its place in an advisory: the incumbent advisory said this in general
# terms; the accounting branch says it with the paragraph the caller can
# read.
ADVISORY_TEXT_AU_ACCOUNTING: str = (
    "This is calculator output, not advice. It is an accounting figure: a "
    "carrying amount computed under AASB 116 (Property, Plant and Equipment) "
    "from the cost, useful life, method and dates supplied in this request, "
    "under the day-count convention stated in this response. It is not a "
    "taxation figure and does not represent a deduction under ITAA 1997 "
    "Division 40 — a separate computation is required for any tax return "
    "or position. Whether the useful life, residual value and depreciation "
    "method are appropriate is a judgement for the entity preparing the "
    "financial statements, and AASB 116 requires those judgements to be "
    "reviewed at each financial year-end (paragraph 51 for useful life and "
    "residual value, paragraph 61 for depreciation method, in each case "
    "treated prospectively under AASB 108 as a change in accounting "
    "estimate); this calculator does not assess them. "
    "Do not carry this figure into a tax return: ITAA 1997 Division 40 "
    "rates and rules differ from the useful-life inputs supplied here, "
    "and the tax-basis figure will not equal this one."
)

ADVISORY_TEXT_UK: str = (
    "This is calculator output, not advice. Consult a registered tax adviser "
    "before relying on these numbers for any return, position, or advice "
    "provided to a third party. Calculator outputs reflect the period-scoped "
    "statutory rate-tables cited in the manifest block; statute may have "
    "changed since the rate-table was last anchored. "
    "Statutory framing: Finance Act 2008 Schedule 41 (penalties for failure "
    "to notify; failure to take reasonable care)."
)

STATUTORY_BASIS_AU = [
    {"statute": "TAA 1953", "section": "s284-15"},
    {"statute": "Tax Agent Services Act 2009", "section": "s50-5"},
]

# Fable D10 mc00-2026-09-04 accounting-basis statutory_basis. The tax-agent
# statutes are replaced by the accounting standards that actually govern
# the figure. Paragraph references stay in the section field for machine
# parseability (matches the shape of the incumbent basis's `section: s284-15`).
STATUTORY_BASIS_AU_ACCOUNTING = [
    {"statute": "AASB 116", "section": "Property, Plant and Equipment"},
    {"statute": "AASB 116", "section": "paragraph 51 (useful life + residual value review)"},
    {"statute": "AASB 116", "section": "paragraph 61 (depreciation method review)"},
    {"statute": "AASB 108", "section": "Accounting Policies, Changes in Accounting Estimates and Errors"},
]

STATUTORY_BASIS_UK = [
    {"statute": "Finance Act 2008", "section": "Schedule 41"},
]


def advisory_block(
    jurisdiction: str = "AU",
    manifest_rate_table_uris: list | None = None,
    basis: str | None = None,
) -> dict[str, Any]:
    """Build the advisory block for a single calculator-invocation response.

    **Fable D6 mc21 2026-09-04:** advisory conditioned on the emitted
    manifest. When `manifest_rate_table_uris` is empty (or None), the
    disclaimer says what depreciation output actually rests on
    (caller-declared inputs; no rate tables consumed).

    **Fable D10 mc00-2026-09-04 (Andrew-raised):** advisory ALSO
    conditioned on `basis`. When `basis == "accounting"`, the disclaimer,
    `statutory_basis`, and `registered_agent_required` shift to the
    accounting-standards frame (AASB 116 + AASB 108) instead of the
    tax-agent frame (TAA + TASA). Same mechanism as D6 (payload-
    conditioning); second discriminator, so FBT and Div7A retain the
    tax-agent framing where it is apt.

    Precedence when both discriminators apply:
        basis == "accounting" wins over manifest-conditional text.
        (The accounting-basis text already covers both the no-rate-
        table observation and the appropriate statutory frame.)

    The returned shape (fields, jurisdiction, statutory_basis) is
    identical across branches; only the `disclaimer` string and
    `statutory_basis` list differ. `registered_agent_required` is
    now branch-conditioned too: True for tax-basis + FBT + Div7A;
    False for accounting basis.
    """
    j = (jurisdiction or "AU").upper()
    b = (basis or "").lower() if basis else None

    if j == "UK":
        # UK forward-looking placeholder unchanged.
        return {
            "disclaimer": ADVISORY_TEXT_UK,
            "registered_agent_required": True,
            "statutory_basis": STATUTORY_BASIS_UK,
            "jurisdiction": "UK",
        }

    # AU — Fable D10 accounting-basis branch takes precedence over D6
    # manifest conditioning.
    if b == "accounting":
        return {
            "disclaimer": ADVISORY_TEXT_AU_ACCOUNTING,
            "registered_agent_required": False,
            "statutory_basis": STATUTORY_BASIS_AU_ACCOUNTING,
            "jurisdiction": "AU",
        }

    # AU — non-accounting basis (tax, FBT, Div7A): Fable D6 manifest
    # conditioning.
    #
    # * `manifest_rate_table_uris is None` (absent / not supplied):
    #   default to the incumbent text — does NOT claim absence, cannot
    #   be a fabrication. Companion test_manifest_fidelity asserts every
    #   registered calculator response carries a manifest, so
    #   missing-manifest is a test failure not a runtime guess.
    # * `manifest_rate_table_uris == []` (explicitly empty): use the
    #   empty-manifest text.
    # * `manifest_rate_table_uris = [...]` (non-empty): use the
    #   incumbent citing-rate-tables text.
    empty_manifest_declared = manifest_rate_table_uris == []
    disclaimer = (
        ADVISORY_TEXT_AU_EMPTY_MANIFEST if empty_manifest_declared
        else ADVISORY_TEXT_AU
    )
    return {
        "disclaimer": disclaimer,
        "registered_agent_required": True,
        "statutory_basis": STATUTORY_BASIS_AU,
        "jurisdiction": "AU",
    }


def wrap_response(
    payload: Mapping[str, Any], jurisdiction: str = "AU",
) -> dict[str, Any]:
    """Attach an ``advisory`` block to a calculator response payload.

    Idempotent: if an advisory block is already present, it is replaced.
    The canonical language always wins; bridges MUST NOT paraphrase or
    weaken (CLAWDOG/110 §5).

    **Fable D6 mc21 2026-09-04:** advisory conditions on
    `payload["manifest"]["rate_table_uris"]`.

    **Fable D10 mc00-2026-09-04:** advisory ALSO conditions on
    `payload["basis"]`. When basis == "accounting", the AASB 116 +
    AASB 108 statutory frame + accounting-branch disclaimer + no-
    registered-agent-required apply. Basis-discrimination beats
    manifest-discrimination when both apply, because the accounting
    text already covers both the no-rate-tables observation and the
    correct statutory frame.
    """
    out = dict(payload)
    manifest_rate_uris = (
        (payload.get("manifest") or {}).get("rate_table_uris")
        if isinstance(payload.get("manifest"), Mapping)
        else None
    )
    basis = payload.get("basis")
    out["advisory"] = advisory_block(
        jurisdiction,
        manifest_rate_table_uris=(
            manifest_rate_uris
            if isinstance(manifest_rate_uris, list)
            else None
        ),
        basis=basis if isinstance(basis, str) else None,
    )
    return out


__all__ = [
    "ADVISORY_TEXT_AU",
    "ADVISORY_TEXT_AU_ACCOUNTING",
    "ADVISORY_TEXT_AU_EMPTY_MANIFEST",
    "ADVISORY_TEXT_UK",
    "STATUTORY_BASIS_AU",
    "STATUTORY_BASIS_AU_ACCOUNTING",
    "STATUTORY_BASIS_UK",
    "advisory_block",
    "wrap_response",
]
