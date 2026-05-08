"""Phase 3a end-to-end contract test.

Production-surface contract test (Lesson #37 anchor — the runway IS the
production surface, not a wind tunnel). This test wires:

    Pydantic input validation
       → FastAPI in-process call
       → mocked Prolog backend (recorded PR-D Case 5 response)
       → manifest-fidelity helper (vendored rate-tables)
       → advisory wrapper
       → pydantic response validation

against the canonical PR-D 5th case (Phase 2l-OC-integrate; CLAWDOG/109 §8.1
exit-criterion).

**Binary-failure gate #3.** Any failure here means the bridge is producing
wrong output for a known good input, regardless of how clean the unit tests
are. The numerical assertions are the load-bearing surface; the manifest +
advisory presence checks are defence-in-depth (the dedicated tests for those
gates live in their own files).
"""
from __future__ import annotations

from urllib.parse import quote

import pytest

CALC_URI = "urn:sbrm:calculator:fbt:car-operating-cost"
PERIOD_URI = "urn:sbrm:period:fbt:fy2026"

# PR-D 5th case input: see tests/fixtures/prolog_response_pr_d_case_5.json
# for the recorded engine response and the computation notes.
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


def _invoke(client) -> dict:
    url = f"/v1/calculators/{quote(CALC_URI, safe='')}/{quote(PERIOD_URI, safe='')}"
    resp = client.post(url, json=PR_D_CASE_5_INPUT)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_phase3a_pr_d_case_5_taxable_value(fastapi_test_client) -> None:
    """The bridge passes through the engine's deterministic taxable_value."""
    body = _invoke(fastapi_test_client)
    assert body["taxable_value"] == pytest.approx(5547.75, abs=0.01)


def test_phase3a_pr_d_case_5_trace_deemed_dispatch(fastapi_test_client) -> None:
    """Deemed-amounts dispatch fires for owned + acquisition data."""
    body = _invoke(fastapi_test_client)
    trace = body["trace"]
    assert trace["deemed_dispatch"] == "computed"
    assert trace["form_of_finance"] == "owned"
    assert trace["deemed_depreciation"] == pytest.approx(13750, abs=0.01)
    assert trace["deemed_interest"] == pytest.approx(4741, abs=0.01)
    assert trace["deemed_total"] == pytest.approx(18491, abs=0.01)


def test_phase3a_pr_d_case_5_manifest_three_entries(fastapi_test_client) -> None:
    """Manifest carries three rate-table entries with valid 64-hex content_hashes."""
    body = _invoke(fastapi_test_client)
    manifest = body["manifest"]
    entries = manifest["rate_table_uris"]
    assert isinstance(entries, list)
    assert len(entries) == 3
    expected_uris = {
        "urn:sbrm:rate:fbt:fy2026:deemed-depreciation-rates",
        "urn:sbrm:rate:fbt:fy2026:benchmark-interest",
        "urn:sbrm:rate:fbt:fy2026:days-in-year",
    }
    assert {e["uri"] for e in entries} == expected_uris
    for entry in entries:
        assert entry["hash_algorithm"] == "sha256"
        assert len(entry["content_hash"]) == 64
        assert all(ch in "0123456789abcdef" for ch in entry["content_hash"])


def test_phase3a_pr_d_case_5_advisory_present_and_cited(fastapi_test_client) -> None:
    """Every calculator response carries a non-empty AU advisory block citing
    TAA 1953 / Tax Agent Services Act."""
    body = _invoke(fastapi_test_client)
    advisory = body["advisory"]
    assert advisory["disclaimer"]
    assert "TAA 1953" in advisory["disclaimer"]
    assert "Tax Agent Services Act" in advisory["disclaimer"]
    assert advisory["registered_agent_required"] is True
    assert advisory["jurisdiction"] == "AU"
    statutes = {(b["statute"], b["section"]) for b in advisory["statutory_basis"]}
    assert ("TAA 1953", "s284-15") in statutes
