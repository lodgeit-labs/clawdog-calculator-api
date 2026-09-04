"""L#105 mc02-2026-09-04 (Fable ruling 12:08 UTC Option A): the gateway
refuses the ambiguity of two deemed-amounts input paths supplied
simultaneously.

**Fable ruling 12:08 UTC verbatim:**

  "L#105 \u2014 ruled: Option A, with C's revisit trigger attached.

   Refuse the ambiguity at the gateway. Reasons, in order:

   1. The engine already refuses it. validate_chained_dv_inputs/2
      throws conflicting_inputs(acquisition_cost,
      opening_depreciated_value). So the gateway is currently laxer
      than the engine it fronts \u2014 it accepts a request the engine
      will reject.
   2. The failure mode is a silent wrong number, not a loud one. Two
      inputs implying different arithmetic, one silently chosen by
      declaration order, returning 5,547.75 where the caller may have
      meant 4,707.25. That is the class the sharing gate exists to
      block.
   3. Refusing asks a question only the caller can answer. Picking for
      them is a guess wearing an answer's clothes.
   4. Option B is already half-shipped and needs no work.
      deemed_dispatch returns 'computed' and 'computed_chained' \u2014
      the trace already names which path fired. That was B's real
      value and it exists.

   Revisit trigger: 'if a consumer ever legitimately needs to supply
   both, that is the trigger to revisit \u2014 and at that point the
   answer is probably an explicit deemed_basis discriminator, not a
   precedence rule.'"

**Response-level assertion discipline** (mc00 08:28 UTC design
covenant): every wire assertion is on parsed JSON of the response body
from `TestClient(app).post(...)`, not on internal validator return
values. The mapper envelope must NOT appear on this refusal path
because L#105 is caught at pydantic tier before dispatch.

**Falsifiability**: this file was written with the fix already in
place. Falsifiability was checked during development by poisoning the
`if conflict_a and conflict_b:` branch to `if False:` and re-running
the tests; 3 of the wire tests fired correctly on the poisoned code
(the fourth is a positive counter-assertion that wouldn't fire).
"""
from __future__ import annotations

from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.schemas.invocation import FBTCarOperatingCostInput

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


def _both_paths_payload() -> dict:
    """Fable's L#105 wire probe shape: both (a) triad and (b) triad
    complete with different implied bases."""
    return {
        "businessUsePercentage": 75,
        "formOfFinance": "owned",
        "employeeContribution": 200,
        "fuelRepairsServicing": 3000,
        "registrationInsurance": 1500,
        "noPrivateUseReduction": 0,
        "acquisitionDate": "2024-04-01",
        # Path (a):
        "openingDepreciatedValue": 55000,
        "daysHeldInFBTYear": 365,
        # Path (b):
        "acquisitionCost": 60000,
    }


# ============================================================================
# Hermetic unit level \u2014 pydantic model construction refuses ambiguity
# ============================================================================


def test_both_paths_supplied_refused_at_model_construction():
    """Fable's L#105 anchor: gateway pydantic MUST refuse when both
    paths (a) and (b) are supplied. Verifies the validator's own
    raise-path independent of the FastAPI route wrapper."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        FBTCarOperatingCostInput(**_both_paths_payload())
    msg = str(exc_info.value)
    # Message names both fields
    assert "openingDepreciatedValue" in msg
    assert "acquisitionCost" in msg
    # Message states the arithmetic divergence
    assert "different arithmetic" in msg
    # Message points to the resolution (send one)
    assert "exactly ONE" in msg
    # Message carries the revisit-trigger reference so a future reader
    # who legitimately needs both can find the escape hatch
    assert "deemed_basis discriminator" in msg


def test_hermetic_only_path_a_still_accepted():
    """Counter-assertion: path (a) alone must still be accepted post-
    L#105. Guards against a poisoning of the ambiguity check that
    would also break the legitimate single-path case."""
    payload = _both_paths_payload()
    payload.pop("acquisitionCost")
    m = FBTCarOperatingCostInput(**payload)
    assert m.opening_depreciated_value == 55000
    assert m.acquisition_cost is None


def test_hermetic_only_path_b_still_accepted():
    """Counter-assertion: path (b) alone must still be accepted post-
    L#105."""
    payload = _both_paths_payload()
    payload.pop("openingDepreciatedValue")
    payload.pop("daysHeldInFBTYear")
    m = FBTCarOperatingCostInput(**payload)
    assert m.acquisition_cost == 60000
    assert m.opening_depreciated_value is None


def test_hermetic_explicit_deemed_total_override_still_accepted():
    """Counter-assertion: path (c) explicit deemedTotal override still
    accepted post-L#105."""
    payload = _both_paths_payload()
    payload.pop("openingDepreciatedValue")
    payload.pop("daysHeldInFBTYear")
    payload.pop("acquisitionCost")
    payload["deemedTotal"] = 18500
    m = FBTCarOperatingCostInput(**payload)
    assert m.deemed_total == 18500


# ============================================================================
# Wire-response level \u2014 the substrate the caller reads (mc00 08:28 UTC)
# ============================================================================


def test_wire_both_paths_returns_gateway_422_json(client: TestClient) -> None:
    """The refusal must surface as HTTP 422 JSON on the wire. Pre-L#105:
    engine surface was HTTP 500 text/plain \u2192 mapper 502 with buried
    diagnostic. Post-L#105: gateway 422 at pydantic tier before dispatch.
    """
    resp = client.post(_url(), json=_both_paths_payload())
    assert resp.status_code == 422, (
        f"L#105 gateway refusal must fire at pydantic 422 tier before "
        f"the engine round-trip. Got {resp.status_code}. Body: "
        f"{resp.text[:400]}"
    )
    assert resp.headers["content-type"].startswith("application/json")


def test_wire_body_names_both_conflicting_fields(client: TestClient) -> None:
    """Wire body must name openingDepreciatedValue AND acquisitionCost \u2014
    the two fields whose simultaneous presence is the ambiguity. Fable's
    cell-29 template discipline: name the conflicting inputs explicitly."""
    resp = client.post(_url(), json=_both_paths_payload())
    body_text = resp.text
    assert "openingDepreciatedValue" in body_text
    assert "acquisitionCost" in body_text


def test_wire_body_states_arithmetic_divergence(client: TestClient) -> None:
    """Fable's ruling: 'say they imply different arithmetic'. The
    refusal message must state WHY the ambiguity matters \u2014 not just
    that two fields are mutually exclusive but that they encode
    different depreciation semantics.

    The template phrase 'different arithmetic' is the load-bearing
    hinge; a caller who reads it knows to pick one deliberately, not
    accidentally.
    """
    resp = client.post(_url(), json=_both_paths_payload())
    body_text = resp.text
    assert "different arithmetic" in body_text
    # Path (a) is opening-WDV-based; path (b) is walk-from-original-cost.
    # Naming both semantics helps the caller pick correctly.
    assert "opening WDV" in body_text or "walk" in body_text


def test_wire_body_names_resolution_path(client: TestClient) -> None:
    """Fable's ruling: 'tell the caller to send one'. The refusal must
    name the resolution explicitly."""
    resp = client.post(_url(), json=_both_paths_payload())
    body_text = resp.text
    assert "exactly ONE" in body_text
    # And the three paths must all be enumerated (Fable cell-29 template).
    assert "(a)" in body_text
    assert "(b)" in body_text
    assert "(c)" in body_text


def test_wire_body_carries_revisit_trigger(client: TestClient) -> None:
    """Fable's ruling 12:08 UTC verbatim: 'if a consumer ever
    legitimately needs to supply both, that is the trigger to revisit
    \u2014 and at that point the answer is probably an explicit
    deemed_basis discriminator, not a precedence rule. Record that as
    the revisit trigger so the next reader does not re-derive it.'

    The wire body itself must carry the revisit-trigger reference so
    a caller with legitimate both-paths semantics knows the escape
    hatch and does not silently give up.
    """
    resp = client.post(_url(), json=_both_paths_payload())
    body_text = resp.text
    assert "deemed_basis discriminator" in body_text


def test_wire_shape_is_pydantic_validation_error_not_mapper_envelope(
    client: TestClient,
) -> None:
    """Design-covenant assertion (mc00 08:28 UTC): L#105 is caught at
    the pydantic layer BEFORE the engine-error mapper. Mapper envelope
    keys must not appear on this refusal path.

    This is the same discipline banked in
    tests/test_mapper_wire_response_shape.py, applied to the L#105
    refusal shape.
    """
    resp = client.post(_url(), json=_both_paths_payload())
    body = resp.json()
    body_str = str(body).lower()
    for mapper_envelope_key in (
        "engine_validation_error",
        "engine_unavailable",
        "engine_bad_request",
        "engine_http_error",
    ):
        assert mapper_envelope_key not in body_str, (
            f"L#105 gateway half caught the defect at pydantic layer, "
            f"so the mapper envelope {mapper_envelope_key!r} must NOT "
            f"appear in the response body. Got: {body}"
        )


# ============================================================================
# Counter-tests \u2014 single-path payloads must NOT trigger the L#105 refusal
# ============================================================================


def test_wire_single_path_a_reaches_engine(client: TestClient) -> None:
    """Path (a) alone must reach the engine path. TestClient has no
    live engine so the response may be a 5xx transport failure, but the
    failure mode MUST NOT be a pydantic 422 mentioning the L#105
    ambiguity.
    """
    payload = _both_paths_payload()
    payload.pop("acquisitionCost")
    resp = client.post(_url(), json=payload)
    if resp.status_code == 422:
        body_text = resp.text
        assert "different arithmetic" not in body_text, (
            f"Path (a) alone should NOT trigger L#105 ambiguity refusal. "
            f"Body: {body_text[:400]}"
        )


def test_wire_single_path_b_reaches_engine(client: TestClient) -> None:
    """Path (b) alone must reach the engine path."""
    payload = _both_paths_payload()
    payload.pop("openingDepreciatedValue")
    payload.pop("daysHeldInFBTYear")
    resp = client.post(_url(), json=payload)
    if resp.status_code == 422:
        body_text = resp.text
        assert "different arithmetic" not in body_text, (
            f"Path (b) alone should NOT trigger L#105 ambiguity refusal. "
            f"Body: {body_text[:400]}"
        )


def test_wire_leased_with_both_paths_is_not_refused(client: TestClient) -> None:
    """L#105 refusal fires only on form_of_finance in {owned,
    hire_purchase}. leased and unspecified are exempt because the
    engine's deemed-amounts dispatch doesn't fire for them anyway."""
    payload = _both_paths_payload()
    payload["formOfFinance"] = "leased"
    resp = client.post(_url(), json=payload)
    if resp.status_code == 422:
        body_text = resp.text
        assert "different arithmetic" not in body_text, (
            f"L#105 must NOT fire on leased form_of_finance. Body: "
            f"{body_text[:400]}"
        )
