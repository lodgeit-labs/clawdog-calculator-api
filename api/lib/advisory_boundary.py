"""Advisory-boundary wrapper.

Implements CLAWDOG/110 §3.2 Non-Negotiable #2 (Advisory-Boundary Contract). Every
calculator-invocation response on every surface MUST carry an ``advisory`` block
citing the relevant statutory framing for the jurisdiction of the calculator.

The literal canonical disclaimer language for AU is supplied here; UK is included
as a forward-looking placeholder. The strings are paraphrases that **cite by
section** (TAA 1953 s284-15, Tax Agent Services Act 2009, Finance Act 2008
Sch41) — they are NOT verbatim transcriptions of statute, which keeps Standing
Rule #11 (Verbatim-Claim Byte-Diff Discipline) clean: no sidecar required.

Lesson #34 anchor — the discipline is to surface the advisory-boundary concern
explicitly at every egress, not to retrofit it after first contact with auditors.
The check is binary: presence or absence on every endpoint that returns
calculator output.
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

STATUTORY_BASIS_UK = [
    {"statute": "Finance Act 2008", "section": "Schedule 41"},
]


def advisory_block(
    jurisdiction: str = "AU",
    manifest_rate_table_uris: list | None = None,
) -> dict[str, Any]:
    """Build the advisory block for a single calculator-invocation response.

    **Fable D6 mc21 2026-09-04:** advisory is conditioned on the emitted
    manifest. When `manifest_rate_table_uris` is empty (or None), the
    disclaimer says what depreciation output actually rests on
    (caller-declared inputs; no rate tables consumed). When it is
    non-empty, the disclaimer cites the manifest as before.

    Conditioning on the emitted manifest rather than on calculator
    identity is load-bearing (Fable verbatim): *"if depreciation ever
    consumes a rate table, the text follows without anyone remembering."*

    The returned shape (fields, jurisdiction, statutory_basis) is
    identical across the two branches; only the `disclaimer` string
    differs.
    """
    j = (jurisdiction or "AU").upper()
    empty_manifest = not manifest_rate_table_uris
    if j == "UK":
        # UK forward-looking placeholder; no empty-manifest variant
        # authored yet because no UK-basis calculator ships. When UK
        # basis populates AND emits an empty manifest, mirror the AU
        # empty-manifest text here.
        return {
            "disclaimer": ADVISORY_TEXT_UK,
            "registered_agent_required": True,
            "statutory_basis": STATUTORY_BASIS_UK,
            "jurisdiction": "UK",
        }
    # Default = AU.
    disclaimer = (
        ADVISORY_TEXT_AU_EMPTY_MANIFEST if empty_manifest
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

    **Fable D6 mc21 2026-09-04:** the advisory text now conditions on
    `payload["manifest"]["rate_table_uris"]`. Empty (or missing)
    manifest yields the empty-manifest disclaimer; non-empty yields the
    original citing-rate-tables text.
    """
    out = dict(payload)
    manifest_rate_uris = (
        (payload.get("manifest") or {}).get("rate_table_uris")
        if isinstance(payload.get("manifest"), Mapping)
        else None
    )
    out["advisory"] = advisory_block(
        jurisdiction,
        manifest_rate_table_uris=(
            manifest_rate_uris
            if isinstance(manifest_rate_uris, list)
            else None
        ),
    )
    return out


__all__ = [
    "ADVISORY_TEXT_AU",
    "ADVISORY_TEXT_AU_EMPTY_MANIFEST",
    "ADVISORY_TEXT_UK",
    "STATUTORY_BASIS_AU",
    "STATUTORY_BASIS_UK",
    "advisory_block",
    "wrap_response",
]
