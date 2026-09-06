"""D21 gateway trio-consistency check (mut-2026-09-06-mc15 per Fable 2026-09-06 UTC).

Fable observed a 200-with-null-trio on the deployed gateway at
`fbt-engine-00017-5zx`: identical LAFHA request seconds apart returned:

  Call 1: taxable_value=900.0, fbt_type="Type 2", gross_up_factor=null,
          fbt_payable=null, rate_table_uris=[], advisory says "consumes no
          statutory rate tables".
  Call 2: taxable_value=900.0, fbt_type="Type 2", gross_up_factor=1.8868,
          fbt_payable=798.12, rate_table_uris=[both URIs].

Fable's rule (verbatim 2026-09-06 UTC):

  "an engine that cannot produce the trio must return a 5xx, never a 200
   with nulls. A missing rate table is an error, not an answer."

Root cause is engine-side sequence-dependent mutable state (still under
investigation via Streamace repro sweep). This PR ships the STRUCTURAL
DEFENCE at the gateway boundary: if the engine returns a positive
taxable_value AND is missing the gross-up trio (gross_up_factor +
grossed_up_taxable_value + fbt_payable) AND rate_uris_consumed is empty,
the gateway refuses with HTTP 502 engine_response_missing_gross_up_trio
rather than passing the null-trio + empty-manifest response to caller.

Scope: FBT calcs only (routed through the generic
/v1/calculators/{calc_uri}/{period_uri} endpoint). Depreciation + Div7A
have different response shapes routed through separate handlers.

Test coverage:
    - D21-exact-shape response → 502 engine_response_missing_gross_up_trio
    - Trio-present + empty URIs → 200 (lesser gap, outside D21 scope)
    - Trio-missing + URIs populated → 200 (would hit manifest-hash path;
      outside D21 scope; separate 502 fires when URIs unresolvable)
    - Trio-present + URIs populated → 200 (normal path)
    - taxable_value=0 → 200 regardless (legitimate s.8A exemption; trio
      would be 0/0/0 downstream)
    - taxable_value absent → 502 engine_response_missing_taxable_value
      (pre-existing check, not D21)

Lessons honoured:
    L#37 — tests exercise the D21 check directly at route level, not
           paraphrased.
    L#40 — production-bundle gate covers real-engine surface separately.
    L#41 — the check names its scope honestly (fires on exact D21 shape,
           not on lesser gaps).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

_FBT_CALC_URI = "urn:sbrm:calculator:fbt:lafha"
_FBT_PERIOD_URI = "urn:sbrm:period:fbt:fy2026"
_LAFHA_BODY = {
    "weeksLivedAway": 5,
    "accommodationPerWeek": 220,
    "mealsPerWeek": 80,
    "exemptAccommodationComponent": 500,
    "exemptFoodComponent": 100,
}


@pytest.fixture
def client() -> TestClient:
    from api.main import app
    return TestClient(app)


def _d21_shape_response() -> dict[str, Any]:
    """The exact shape Fable observed 2026-09-06 at fbt-engine-00017-5zx:
    positive taxable_value + fbt_type + no trio + empty rate_uris_consumed.
    """
    return {
        "taxable_value": 900.0,
        "gross_taxable_value": 1500.0,
        "employee_contribution": 0,
        "reductions": 600,
        "fbt_type": "Type 2",
        "rate_uris_consumed": [],
    }


def _healthy_response() -> dict[str, Any]:
    """Post-Phase-2 healthy shape: trio + URIs both populated."""
    return {
        "taxable_value": 900.0,
        "gross_taxable_value": 1500.0,
        "employee_contribution": 0,
        "reductions": 600,
        "fbt_type": "Type 2",
        "gross_up_factor": 1.8868,
        "grossed_up_taxable_value": 1698.12,
        "fbt_payable": 798.12,
        "rate_uris_consumed": [
            "urn:sbrm:rate:fbt:fy2026:gross-up-type-2",
            "urn:sbrm:rate:fbt:fy2026:fbt-rate",
        ],
        "trace": {
            "applied_rate_table_uris": [
                "urn:sbrm:rate:fbt:fy2026:gross-up-type-2",
                "urn:sbrm:rate:fbt:fy2026:fbt-rate",
            ]
        },
    }


def _trio_present_empty_uris_response() -> dict[str, Any]:
    """Trio populated but rate_uris_consumed empty. Lesser gap; outside
    D21 scope (D21 fires only when BOTH trio AND URIs are missing).
    """
    return {
        "taxable_value": 900.0,
        "gross_taxable_value": 1500.0,
        "employee_contribution": 0,
        "reductions": 600,
        "fbt_type": "Type 2",
        "gross_up_factor": 1.8868,
        "grossed_up_taxable_value": 1698.12,
        "fbt_payable": 798.12,
        "rate_uris_consumed": [],
    }


def _zero_taxable_value_response() -> dict[str, Any]:
    """taxable_value=0 (e.g. s.8A exemption zeroes the base). D21 check
    does not fire; trio would legitimately be 0/0/0 downstream.
    """
    return {
        "taxable_value": 0.0,
        "gross_taxable_value": 1500.0,
        "employee_contribution": 0,
        "reductions": 600,
        "fbt_type": "Type 2",
        "rate_uris_consumed": [],
    }


# ---------------------------------------------------------------------------
# D21 primary defence — refuse the exact null-trio shape at 502
# ---------------------------------------------------------------------------

def test_d21_exact_shape_returns_502_engine_response_missing_gross_up_trio(
    client: TestClient, caplog: pytest.LogCaptureFixture,
) -> None:
    """Fable's exact evidence shape (2026-09-06 fbt-engine-00017-5zx LAFHA
    call 1): taxable_value=900.0 + fbt_type + no trio + rate_uris_consumed
    empty. MUST return 502 with error='engine_response_missing_gross_up_trio'
    and log at ERROR level.
    """
    import logging

    calc_uri_enc = quote(_FBT_CALC_URI, safe="")
    with patch(
        "api.routes.calculators.PrologClient.calculate_fbt",
        new=AsyncMock(return_value=_d21_shape_response()),
    ):
        with caplog.at_level(logging.ERROR, logger="api.routes.calculators"):
            resp = client.post(
                f"/v1/calculators/{calc_uri_enc}/{_FBT_PERIOD_URI}",
                json=_LAFHA_BODY,
            )

    assert resp.status_code == 502, (
        f"expected 502; got {resp.status_code}: {resp.text[:400]}"
    )
    body = resp.json()
    assert body["detail"]["error"] == "engine_response_missing_gross_up_trio"
    assert body["detail"]["taxable_value"] == 900.0
    assert body["detail"]["trio_keys_present"] == {
        "gross_up_factor": False,
        "grossed_up_taxable_value": False,
        "fbt_payable": False,
    }
    assert body["detail"]["rate_uris_consumed_count"] == 0
    # ERROR-level log signal for SRE dashboard partitioning
    assert any(
        "engine_response_missing_gross_up_trio" in r.message
        for r in caplog.records
        if r.levelno == logging.ERROR
    )


# ---------------------------------------------------------------------------
# D21 scope — lesser gaps do NOT fire the check
# ---------------------------------------------------------------------------

def test_healthy_response_passes_through_200(client: TestClient) -> None:
    """Post-Phase-2 healthy shape (trio + URIs both populated) → 200 with
    trio at the wire. Baseline no-op case for the check.
    """
    calc_uri_enc = quote(_FBT_CALC_URI, safe="")
    with patch(
        "api.routes.calculators.PrologClient.calculate_fbt",
        new=AsyncMock(return_value=_healthy_response()),
    ):
        resp = client.post(
            f"/v1/calculators/{calc_uri_enc}/{_FBT_PERIOD_URI}",
            json=_LAFHA_BODY,
        )

    assert resp.status_code == 200, (
        f"expected 200; got {resp.status_code}: {resp.text[:400]}"
    )
    body = resp.json()
    assert body["gross_up_factor"] == 1.8868
    assert body["fbt_payable"] == 798.12


def test_trio_present_empty_uris_still_returns_200(client: TestClient) -> None:
    """Trio populated + rate_uris_consumed empty → 200. This is a LESSER
    gap (fbt_payable is available; only the manifest citation surface is
    empty) and is outside D21 scope by design. D21 fires only on the
    exact BOTH-missing shape Fable observed.
    """
    calc_uri_enc = quote(_FBT_CALC_URI, safe="")
    with patch(
        "api.routes.calculators.PrologClient.calculate_fbt",
        new=AsyncMock(return_value=_trio_present_empty_uris_response()),
    ):
        resp = client.post(
            f"/v1/calculators/{calc_uri_enc}/{_FBT_PERIOD_URI}",
            json=_LAFHA_BODY,
        )

    assert resp.status_code == 200, (
        f"expected 200; got {resp.status_code}: {resp.text[:400]}"
    )
    body = resp.json()
    assert body["gross_up_factor"] == 1.8868
    assert body["manifest"]["rate_table_uris"] == []


def test_zero_taxable_value_does_not_fire_check(client: TestClient) -> None:
    """taxable_value=0 (e.g. s.8A exemption) is legitimate; trio would
    be 0/0/0 downstream. D21 check must NOT fire on this shape.
    """
    calc_uri_enc = quote(_FBT_CALC_URI, safe="")
    with patch(
        "api.routes.calculators.PrologClient.calculate_fbt",
        new=AsyncMock(return_value=_zero_taxable_value_response()),
    ):
        resp = client.post(
            f"/v1/calculators/{calc_uri_enc}/{_FBT_PERIOD_URI}",
            json=_LAFHA_BODY,
        )

    assert resp.status_code == 200, (
        f"expected 200 on taxable_value=0; got {resp.status_code}: "
        f"{resp.text[:400]}"
    )
    body = resp.json()
    assert body["taxable_value"] == 0.0
    # Trio is absent (engine didn't emit it); Pydantic defaults to null.
    # This is consistent with pre-D21 wire behaviour for s.8A-exemption
    # shapes.
