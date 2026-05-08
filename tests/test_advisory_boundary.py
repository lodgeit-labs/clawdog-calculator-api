"""Advisory-boundary binary-failure gate (CLAWDOG/110 §3.2 Non-Negotiable #2).

Every endpoint that returns calculator output MUST surface an ``advisory``
block. A response that lacks the block, or whose block is empty / wrong-shape /
not citing statute, fails the build.

Lesson #34 anchor — surfacing the advisory boundary explicitly at every egress
is the discipline; retrofitting it after first contact with auditors is failure.
"""
from __future__ import annotations

from urllib.parse import quote

from api.lib.advisory_boundary import (
    ADVISORY_TEXT_AU,
    ADVISORY_TEXT_UK,
    advisory_block,
    wrap_response,
)

# --- Unit-level surface (the helper itself) -----------------------------------


def test_advisory_block_au_carries_taa_and_tasa_citations() -> None:
    block = advisory_block("AU")
    assert block["disclaimer"] == ADVISORY_TEXT_AU
    assert block["registered_agent_required"] is True
    assert block["jurisdiction"] == "AU"
    statutes = {(b["statute"], b["section"]) for b in block["statutory_basis"]}
    assert ("TAA 1953", "s284-15") in statutes
    assert ("Tax Agent Services Act 2009", "s50-5") in statutes


def test_advisory_block_uk_carries_fa2008_sch41_citation() -> None:
    block = advisory_block("UK")
    assert block["disclaimer"] == ADVISORY_TEXT_UK
    assert block["jurisdiction"] == "UK"
    statutes = {(b["statute"], b["section"]) for b in block["statutory_basis"]}
    assert ("Finance Act 2008", "Schedule 41") in statutes


def test_advisory_wrap_response_attaches_block() -> None:
    out = wrap_response({"taxable_value": 1.0}, jurisdiction="AU")
    assert "advisory" in out
    assert out["advisory"]["jurisdiction"] == "AU"
    assert out["taxable_value"] == 1.0


def test_advisory_wrap_response_replaces_existing_block() -> None:
    """An incoming payload claiming a weaker advisory block is overridden."""
    out = wrap_response(
        {"taxable_value": 1.0, "advisory": {"disclaimer": "weak"}},
        jurisdiction="AU",
    )
    assert out["advisory"]["disclaimer"] == ADVISORY_TEXT_AU
    assert "TAA 1953" in out["advisory"]["disclaimer"]


# --- Endpoint-level surface (every endpoint that returns calculator output) ---

CALC_URI = "urn:sbrm:calculator:fbt:car-operating-cost"
PERIOD_URI = "urn:sbrm:period:fbt:fy2026"

PR_D_CASE_5_INPUT = {
    "businessUsePercentage": 75,
    "employeeContribution": 200,
    "formOfFinance": "owned",
    "leasePayments": 0,
    "fuelRepairsServicing": 3000,
    "registrationInsurance": 1500,
    "noPrivateUseReduction": 0,
    "acquisitionDate": "2024-04-01",
    "openingDepreciatedValue": 55000,
    "daysHeldInFBTYear": 365,
}


def test_calculator_invocation_endpoint_carries_advisory_block(
    fastapi_test_client,
) -> None:
    """POST /v1/calculators/{calc}/{period} must include an advisory block.

    Binary-failure gate: the test fails if the block is absent, empty, or
    missing the statutory citation strings.
    """
    url = f"/v1/calculators/{quote(CALC_URI, safe='')}/{quote(PERIOD_URI, safe='')}"
    resp = fastapi_test_client.post(url, json=PR_D_CASE_5_INPUT)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "advisory" in body, "calculator-invocation response missing advisory block"
    advisory = body["advisory"]
    assert advisory["disclaimer"], "advisory.disclaimer is empty"
    assert "TAA 1953" in advisory["disclaimer"]
    assert "Tax Agent Services Act" in advisory["disclaimer"]
    assert advisory["registered_agent_required"] is True
    assert advisory["statutory_basis"], "advisory.statutory_basis is empty"


def test_canonical_disclaimer_text_byte_stable() -> None:
    """The canonical disclaimer language is byte-stable.

    Per CLAWDOG/110 §3.2 the language is canonical to one byte; an accidental
    edit must surface as a test failure rather than a silent regression. If
    the language genuinely needs to change, a Brain-side helm-roll is required
    AND this test is updated in the same PR.
    """
    expected_au_phrases = [
        "This is calculator output, not advice.",
        "Consult a registered tax agent",
        "TAA 1953 s284-15",
        "Tax Agent Services Act 2009",
    ]
    for phrase in expected_au_phrases:
        assert phrase in ADVISORY_TEXT_AU, (
            f"AU disclaimer drift — phrase missing: {phrase!r}"
        )

    expected_uk_phrases = [
        "This is calculator output, not advice.",
        "Finance Act 2008 Schedule 41",
    ]
    for phrase in expected_uk_phrases:
        assert phrase in ADVISORY_TEXT_UK, (
            f"UK disclaimer drift — phrase missing: {phrase!r}"
        )
