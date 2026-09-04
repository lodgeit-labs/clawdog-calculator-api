"""D18 gateway half: fail-open-on-unsatisfied-conjunction-guard defence
in depth for COC deemed-amounts input.

**Fable rulings mc01-2026-09-04 09:00 UTC + 09:11 UTC (verbatim):**

  "The real shape is now clear, and it is D8a's shape one calculator
   over: the gateway accepts a request that cannot produce a correct
   answer, and the engine computes a different thing rather than
   refusing. Remedy mirrors the basis-conditional work exactly —
   gateway requires the triad conditionally on form_of_finance ∈
   {owned, hire_purchase}; engine refuses with a typed refusal
   instead of falling through. Neither relies on the other."

  "On D18 — do not change the arithmetic yet, and this is a ruling
   not a preference. Your figures check ... But you have two
   secondary sources and no primary, on a headline calculator, for a
   $4,643 correction. That is the mediated-substrate shape — and we
   have an oracle built for exactly this case. Send the cell-21
   control payload to Waqas."

**IMPORTANT SCOPE NOTE**: This gateway defence-in-depth changes WHICH
PAYLOADS reach the fold, NOT what the fold computes. The D18
arithmetic (whether deemed depreciation + deemed interest should be
added to operating cost C for owned cars) remains BLOCKED pending
Waqas oracle concordance. This validator ensures the FAIL-OPEN wire
signature Fable observed at cell 21 cannot fire from the gateway; it
does NOT ensure the engine's arithmetic is correct.

The three accepted paths mirror the engine's `fbt_oc_deemed_dispatch/8`
dispatch branches at `LodgeiT_FBT/FBT_Engine.pl:1873-1946`:

  (a) single-year-primitive: openingDepreciatedValue + daysHeldInFBTYear
      + acquisitionDate — the pre-Rung 3 legacy path.

  (b) chained-DV walk: acquisitionCost + acquisitionDate
      (+ optional daysHeldInFBTYear). Engine defaults days_held to
      full-FY for this path only.

  (c) explicit override: deemedTotal supplied. Engine uses the value
      directly and skips the deemed-amounts predicates.

For leased or unspecified form_of_finance the validator is a no-op:
the engine's dispatch does not enter the deemed-amounts branch, so
the conjunction-guard is not required.

**Wire-response test discipline** (mc00 08:28 UTC design covenant):
every assertion is on parsed JSON of the response body from
`TestClient(app).post(...)`.
"""
from __future__ import annotations

from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.main import app

COC_URI = "urn:sbrm:calculator:fbt:car-operating-cost"
PERIOD_URI = "urn:sbrm:period:fbt:fy2026"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _url() -> str:
    return (
        f"/v1/calculators/{quote(COC_URI, safe='')}/"
        f"{quote(PERIOD_URI, safe='')}"
    )


def _minimal_valid_owned_coc_no_triad() -> dict:
    """Cell 21's shape: form_of_finance='owned' with acquisitionDate +
    openingDepreciatedValue but NO daysHeldInFBTYear. This is the shape
    the engine currently silently defaults on.
    """
    return {
        "businessUsePercentage": 75,
        "formOfFinance": "owned",
        "employeeContribution": 200,
        "fuelRepairsServicing": 3000,
        "registrationInsurance": 1500,
        "noPrivateUseReduction": 0,
        "acquisitionDate": "2024-04-01",
        "openingDepreciatedValue": 55000,
        # daysHeldInFBTYear DELIBERATELY MISSING
    }


# ============================================================================
# Cell 21 replay — gateway refuses the fail-open payload
# ============================================================================


def test_cell21_owned_without_days_held_is_refused_at_gateway_422(
    client: TestClient,
) -> None:
    """Cell 21 replay against the mounted app. The exact wire payload
    Fable used to expose the D18 silent-default now refuses at the
    gateway 422 tier BEFORE the engine round-trip.

    Pre-D18-gateway-half wire evidence: HTTP 200 with
    `taxable_value: 925.00` and `trace.deemed_dispatch: skipped_no_acquisition`
    (materially understated per FBTAA s10 — arithmetic itself blocked
    pending Waqas oracle).

    Post-D18-gateway-half: HTTP 422 naming the missing key.
    """
    resp = client.post(_url(), json=_minimal_valid_owned_coc_no_triad())
    assert resp.status_code == 422, (
        f"D18 gateway half: owned/hire_purchase COC payload missing "
        f"daysHeldInFBTYear must be refused at pydantic 422, not "
        f"forwarded to the engine where the fold silently defaults to "
        f"deemed_total=0. Body: {resp.text[:400]}"
    )
    assert resp.headers["content-type"].startswith("application/json")
    body_text = resp.text
    # The refusal must name daysHeldInFBTYear so the caller knows what's
    # missing.
    assert "daysHeldInFBTYear" in body_text, (
        f"Refusal must name the missing key. Fable's diagnostic-label "
        f"discipline mc01 09:11 UTC: 'A diagnostic label names the "
        f"condition that was actually unsatisfied, or it names none of "
        f"them.' Got: {body_text[:400]}"
    )


def test_cell21_shape_also_lists_alternative_paths(client: TestClient) -> None:
    """The refusal message must enumerate the three alternative paths
    (single-year-primitive triad / chained-DV walk triad / explicit
    override) so a caller knows the full set of legitimate payloads.
    Fable's discipline: the message names what's missing AND what the
    alternatives are, not just the first thing that failed.
    """
    resp = client.post(_url(), json=_minimal_valid_owned_coc_no_triad())
    assert resp.status_code == 422
    body_text = resp.text
    # Path (a) is what the caller was closest to; must be named.
    assert "single-year-primitive" in body_text or "openingDepreciatedValue" in body_text
    # Paths (b) and (c) should also appear so the caller sees the full set.
    assert "chained-DV" in body_text or "acquisitionCost" in body_text
    assert "deemedTotal" in body_text or "explicit override" in body_text


# ============================================================================
# The three legitimate paths must pass pydantic
# ============================================================================


def test_path_a_single_year_primitive_triad_passes(client: TestClient) -> None:
    """Path (a) satisfied: all three of openingDepreciatedValue +
    daysHeldInFBTYear + acquisitionDate. Payload passes pydantic; any
    non-422 response is fine (5xx transport failures under TestClient
    with no live engine are expected)."""
    payload = _minimal_valid_owned_coc_no_triad()
    payload["daysHeldInFBTYear"] = 365
    resp = client.post(_url(), json=payload)
    if resp.status_code == 422:
        body_text = resp.text
        # Only assertion: not a 422 caused by our conjunction-guard.
        assert "single-year-primitive" not in body_text, (
            f"Path (a) satisfied should NOT trigger conjunction-guard. "
            f"Body: {body_text[:400]}"
        )


def test_path_b_chained_dv_walk_triad_passes(client: TestClient) -> None:
    """Path (b) satisfied: acquisitionCost + acquisitionDate (with
    optional daysHeldInFBTYear). Payload passes pydantic even without
    openingDepreciatedValue."""
    payload = _minimal_valid_owned_coc_no_triad()
    # Swap opening_depreciated_value for acquisition_cost (they are
    # mutually exclusive per engine's Lesson #14 strict-validation).
    payload.pop("openingDepreciatedValue")
    payload["acquisitionCost"] = 55000
    resp = client.post(_url(), json=payload)
    if resp.status_code == 422:
        body_text = resp.text
        assert "chained-DV" not in body_text, (
            f"Path (b) satisfied should NOT trigger conjunction-guard. "
            f"Body: {body_text[:400]}"
        )


def test_path_c_explicit_deemed_total_override_passes(
    client: TestClient,
) -> None:
    """Path (c) satisfied: explicit deemedTotal supplied. Payload passes
    pydantic even without the acquisition inputs."""
    payload = _minimal_valid_owned_coc_no_triad()
    payload.pop("acquisitionDate")
    payload.pop("openingDepreciatedValue")
    payload["deemedTotal"] = 18500
    resp = client.post(_url(), json=payload)
    if resp.status_code == 422:
        body_text = resp.text
        assert "deemedTotal" not in body_text, (
            f"Path (c) satisfied should NOT trigger conjunction-guard. "
            f"Body: {body_text[:400]}"
        )


# ============================================================================
# leased / unspecified are NOT subject to the conjunction-guard
# ============================================================================


@pytest.mark.parametrize("form", ["leased", "unspecified"])
def test_leased_and_unspecified_do_not_require_triad(
    client: TestClient, form: str
) -> None:
    """The conjunction-guard fires only on owned/hire_purchase. leased
    engine-path is `skipped_leased` (no deemed amounts by design per
    FBTAA leased-car provisions). unspecified engine-path is
    `skipped_no_acquisition` but that's the correct treatment for an
    unspecified form_of_finance."""
    payload = _minimal_valid_owned_coc_no_triad()
    payload["formOfFinance"] = form
    resp = client.post(_url(), json=payload)
    if resp.status_code == 422:
        body_text = resp.text
        # Only assertion: not a 422 caused by the conjunction-guard.
        assert (
            "single-year-primitive" not in body_text
            and "chained-DV" not in body_text
        ), (
            f"form_of_finance={form!r} should NOT trigger the "
            f"conjunction-guard (it fires only on owned/hire_purchase). "
            f"Body: {body_text[:400]}"
        )


# ============================================================================
# Wire-response envelope shape (mc00 08:28 UTC design covenant)
# ============================================================================


def test_wire_refusal_shape_is_pydantic_validation_error(
    client: TestClient,
) -> None:
    """Design-covenant assertion: cell 21 shape is caught at the
    pydantic layer BEFORE the engine-error mapper. Mapper envelope
    keys must not appear on the pydantic-refusal path."""
    resp = client.post(_url(), json=_minimal_valid_owned_coc_no_triad())
    assert resp.status_code == 422
    body = resp.json()
    body_str = str(body).lower()
    for mapper_envelope_key in (
        "engine_validation_error",
        "engine_unavailable",
        "engine_bad_request",
    ):
        assert mapper_envelope_key not in body_str, (
            f"D18 gateway half caught the defect at pydantic layer, so "
            f"the mapper envelope {mapper_envelope_key!r} must NOT "
            f"appear in the response body. Got: {body}"
        )
    # pydantic emits validation-error `detail` as a list.
    detail = body.get("detail", [])
    assert isinstance(detail, list) or isinstance(detail, str), (
        f"pydantic validation-error detail expected list or string. "
        f"Got: {detail!r}"
    )
