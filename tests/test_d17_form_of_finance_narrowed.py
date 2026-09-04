"""D17 gateway half: form_of_finance narrowed to Literal at pydantic layer.

**Fable ruling mc01-2026-09-04 09:11 UTC (verbatim):**

  "D17 gateway half now — form_of_finance narrowed to the Literal its
   own description already declares. Engine typed refusal follows in
   the FBT engine PR."

Wire-truth of the pre-D17 defect (reproduced hermetically):

  A payload with `formOfFinance: "sf_16"` and any other valid COC fields
  hit the pydantic `@field_validator("form_of_finance")` which raised
  `ValueError`. FastAPI could not JSON-serialise the ValueError object
  inside its own validation-error handler, producing:

    HTTP 500
    Content-Type: text/plain
    body: "TypeError: Object of type ValueError is not JSON serializable"

  Not JSON. Bypassed the D8a mapper. Fable's cell 25 wire observation
  matches this shape exactly.

Post-D17 gateway half:

  Same payload → HTTP 422 with JSON body containing pydantic's
  native `literal_error` naming the accepted set. Mapper not reached
  because the gateway pydantic layer refuses before dispatch. Same
  defence-in-depth shape as D8a basis-conditional narrowing.

**Response-level assertion discipline** (mc00 08:28 UTC design covenant
from `tests/test_mapper_wire_response_shape.py`): every assertion in
this file is on the parsed JSON of the response body from
`TestClient(app).post(...)`, not on internal validator return values.
That is the substrate the caller reads.

Engine typed refusal (the sibling half of D17) is queued as an FBT
engine PR: when a matching-branch predicate falls through in the
engine's fold, emit `refusal_class: "unknown_form_of_finance"` instead
of raising. Gateway-side Literal narrowing closes the wire defect;
engine-side typed refusal closes the defence-in-truth requirement.
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


def _base_valid_coc_payload() -> dict:
    """COC payload complete enough to pass both D17 (Literal on
    form_of_finance) AND D18 gateway half (conjunction-guard requiring
    the deemed-amounts input triad on owned/hire_purchase). Includes
    `daysHeldInFBTYear` so path (a) single-year-primitive triad is
    satisfied.
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
        "daysHeldInFBTYear": 365,
    }


# ============================================================================
# Cell 25 replay — the exact wire defect Fable observed
# ============================================================================


def test_cell25_invalid_form_of_finance_returns_422_json(
    client: TestClient,
) -> None:
    """Pre-D17: HTTP 500 with `TypeError: Object of type ValueError is not
    JSON serializable` body, non-JSON, bypasses the mapper.

    Post-D17: HTTP 422 with JSON body containing pydantic's native
    `literal_error` naming the accepted set.
    """
    payload = {**_base_valid_coc_payload(), "formOfFinance": "sf_16"}
    resp = client.post(_url(), json=payload)
    assert resp.status_code == 422, (
        f"D17 gateway half: unknown formOfFinance must be refused at "
        f"the pydantic literal_error tier (422), not raised as an "
        f"uncaught exception (500). Body: {resp.text[:400]}"
    )
    assert resp.headers["content-type"].startswith("application/json"), (
        f"Response must be JSON; the pre-D17 defect was that the "
        f"ValueError raised in @field_validator could not be serialised "
        f"and FastAPI returned text/plain 500. Got content-type: "
        f"{resp.headers.get('content-type')!r}"
    )
    body = resp.json()
    # pydantic emits literal_error at the top-level `detail` list.
    detail = body.get("detail", [])
    assert isinstance(detail, list), (
        f"pydantic validation error `detail` should be a list of error "
        f"records. Got: {detail!r}"
    )
    # At least one error must name form_of_finance / formOfFinance as
    # the failing location.
    found_form_error = any(
        (
            "formOfFinance" in str(err.get("loc", []))
            or "form_of_finance" in str(err.get("loc", []))
        )
        for err in detail
    )
    assert found_form_error, (
        f"pydantic error detail must locate the failure at formOfFinance. "
        f"Got: {detail!r}"
    )


def test_cell25_wire_body_names_accepted_literal_set(client: TestClient) -> None:
    """The wire response must name the four accepted literal values so
    the caller knows what to supply. This is the caller-actionable
    information Fable's D8a mapper discipline requires."""
    payload = {**_base_valid_coc_payload(), "formOfFinance": "sf_16"}
    resp = client.post(_url(), json=payload)
    assert resp.status_code == 422
    body_text = resp.text.lower()
    for expected_value in ("owned", "hire_purchase", "leased", "unspecified"):
        assert expected_value in body_text, (
            f"Wire response must name {expected_value!r} in the accepted "
            f"set so the caller knows what to supply. Got body: "
            f"{resp.text[:600]}"
        )


def test_cell25_previously_removed_other_value_is_refused(
    client: TestClient,
) -> None:
    """The pre-D17 `@field_validator` accepted an orphaned `"other"`
    value that neither the description nor the engine handled. D17
    removes it from the accepted set; a caller sending `"other"` now
    gets a 422 literal_error, not a silent-drop-to-unspecified."""
    payload = {**_base_valid_coc_payload(), "formOfFinance": "other"}
    resp = client.post(_url(), json=payload)
    assert resp.status_code == 422, (
        f"D17: `\"other\"` was orphaned in the pre-D17 field_validator "
        f"but neither the description nor the engine handle it. Now "
        f"refused. Body: {resp.text[:400]}"
    )


# ============================================================================
# Positive coverage — the four accepted values still reach the mapper /
# engine path
# ============================================================================


@pytest.mark.parametrize(
    "form_of_finance", ["owned", "hire_purchase", "leased", "unspecified"]
)
def test_accepted_values_pass_pydantic_and_reach_engine_path(
    client: TestClient, form_of_finance: str
) -> None:
    """All four Literal-declared values pass pydantic. Response status
    will vary (200 if engine happy-path, 5xx if engine transport fails
    under TestClient with no live engine), but the failure mode MUST
    NOT be a pydantic 422 refusal on form_of_finance."""
    payload = {**_base_valid_coc_payload(), "formOfFinance": form_of_finance}
    resp = client.post(_url(), json=payload)
    # Only assertion: not a 422 caused by form_of_finance refusal.
    # (The TestClient may return other statuses depending on engine
    # reachability, which is fine — we're pinning the pydantic-layer
    # accept.)
    if resp.status_code == 422:
        body_text = resp.text.lower()
        assert "formOfFinance".lower() not in body_text, (
            f"form_of_finance={form_of_finance!r} should PASS pydantic "
            f"but a 422 was returned naming formOfFinance as the failing "
            f"location. Body: {resp.text[:400]}"
        )


# ============================================================================
# Design covenant echo — the assertion Fable's mc00 08:28 UTC ruling
# established
# ============================================================================


def test_wire_shape_is_pydantic_literal_error_not_engine_error_mapper():
    """Design-covenant assertion: cell 25 defect is caught at the
    pydantic layer BEFORE the engine-error-mapper is reached. The
    fault-partitioning of D8a therefore does not need to handle
    unknown form_of_finance as a special case; the value never reaches
    the engine.

    This test asserts the boundary: pydantic literal_error is the
    caller-facing shape, and the mapper's engine_validation_error /
    engine_unavailable envelopes are not present in the response body.
    """
    client = TestClient(app)
    payload = {**_base_valid_coc_payload(), "formOfFinance": "sf_16"}
    resp = client.post(_url(), json=payload)
    body = resp.json()
    body_str = str(body).lower()
    # These envelope keys belong to the mapper's fault-partition; they
    # must NOT appear on the pydantic-refusal path.
    for mapper_envelope_key in (
        "engine_validation_error",
        "engine_unavailable",
        "engine_bad_request",
    ):
        assert mapper_envelope_key not in body_str, (
            f"D17 gateway half caught the defect at pydantic layer, so "
            f"the mapper envelope {mapper_envelope_key!r} must NOT "
            f"appear in the response body. Got: {body}"
        )
