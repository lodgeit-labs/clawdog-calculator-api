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


def advisory_block(jurisdiction: str = "AU") -> dict[str, Any]:
    """Build the advisory block for a single calculator-invocation response.

    The returned shape is identical across calculators within a jurisdiction.
    """
    j = (jurisdiction or "AU").upper()
    if j == "UK":
        return {
            "disclaimer": ADVISORY_TEXT_UK,
            "registered_agent_required": True,
            "statutory_basis": STATUTORY_BASIS_UK,
            "jurisdiction": "UK",
        }
    # Default = AU. The Phase 3a constellation is AU-only; UK is forward-looking.
    return {
        "disclaimer": ADVISORY_TEXT_AU,
        "registered_agent_required": True,
        "statutory_basis": STATUTORY_BASIS_AU,
        "jurisdiction": "AU",
    }


def wrap_response(payload: Mapping[str, Any], jurisdiction: str = "AU") -> dict[str, Any]:
    """Attach an ``advisory`` block to a calculator response payload.

    Idempotent: if an advisory block is already present, it is replaced. The
    canonical language always wins; bridges MUST NOT paraphrase or weaken
    (CLAWDOG/110 §5).
    """
    out = dict(payload)
    out["advisory"] = advisory_block(jurisdiction)
    return out


__all__ = [
    "ADVISORY_TEXT_AU",
    "ADVISORY_TEXT_UK",
    "STATUTORY_BASIS_AU",
    "STATUTORY_BASIS_UK",
    "advisory_block",
    "wrap_response",
]
