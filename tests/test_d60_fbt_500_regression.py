"""D60 FBT-500 regression (Fable [CALC] 2026-09-30).

Revision 00054-lh7 (commit 482e7df, PR #52) served a bare HTTP 500 on every FBT
calculator: the live FBT engine emits a top-level ``rounding_policy`` which
``build_manifest`` copies into ``manifest.rounding_policy``, but the FBT route's
``CalculatorInvocationResponse.manifest`` (``Manifest``, ``extra="forbid"``) did
not declare that field, so response validation raised ``extra_forbidden`` — an
unhandled ``ValidationError`` → bare 500. The gateway smoke stub predates D60
(no top-level ``rounding_policy``), so no test caught it.

These route-level tests stub the engine HTTP call to a realistic 200 body that
INCLUDES ``rate_uris_consumed`` and a top-level ``rounding_policy`` (as the live
engine now does) and assert 200 + ``manifest.rounding_policy`` + the D60 advisory
sentence — for an FBT URN and for hp:schedule.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.prolog_client import PrologClient
from api.routes.calculators import get_prolog_client

_FBT_ENGINE_BODY = json.loads(
    (Path(__file__).parent / "fixtures" / "prolog_response_pr_d_case_5.json").read_text()
)
# The live FBT engine (post-#67) emits rounding_policy as a top-level string.
_FBT_ENGINE_BODY = {**_FBT_ENGINE_BODY, "rounding_policy": "lodgeit-rounding-1.0"}

_FBT_ROUTE = (
    "/v1/calculators/urn%3Asbrm%3Acalculator%3Afbt%3Acar-operating-cost"
    "/urn%3Asbrm%3Aperiod%3Afbt%3Afy2026"
)
_FBT_PAYLOAD = {
    "businessUsePercentage": 75,
    "formOfFinance": "owned",
    "fuelRepairsServicing": 3000,
    "registrationInsurance": 1500,
    "employeeContribution": 200,
    "noPrivateUseReduction": 0,
    "acquisitionCost": 50000,
    "acquisitionDate": "2024-01-01",
}


@pytest.fixture
def fbt_engine_stubbed_client():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calculate_fbt" and request.method == "POST":
            return httpx.Response(200, json=_FBT_ENGINE_BODY)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "rate_table_facts": 99})
        return httpx.Response(404, json={"error": "no fixture"})

    mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def _override() -> PrologClient:
        return PrologClient(base_url="http://prolog.test", client=mock)

    app.dependency_overrides[get_prolog_client] = _override
    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_prolog_client, None)


def test_fbt_route_200_with_rounding_policy_and_advisory(fbt_engine_stubbed_client):
    """FBT route no longer 500s when the engine emits a top-level
    rounding_policy; the manifest carries it and the advisory sentence is
    appended."""
    resp = fbt_engine_stubbed_client.post(_FBT_ROUTE, json=_FBT_PAYLOAD)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["manifest"]["rounding_policy"] == "lodgeit-rounding-1.0"
    assert "lodgeit-rounding-1.0" in body["advisory"]["disclaimer"]
    assert "single-figure calculator" in body["advisory"]["disclaimer"]


def test_hp_schedule_advisory_carries_rounding_sentence():
    """hp:schedule advisory notes include the D60 rounding sentence."""
    with TestClient(app, raise_server_exceptions=True) as client:
        resp = client.post(
            "/v1/calculators/hp/schedule",
            json={
                "amount_financed": "50000.00",
                "annual_rate_pct": "7.25",
                "term_regular_instalments": 60,
                "instalment": "1000.00",
                "timing": "in_arrears",
                "frequency": "monthly",
                "begin_date": "2024-07-01",
                "contract_form": "hire_purchase",
            },
        )
    assert resp.status_code == 200, resp.text
    notes = resp.json()["advisory"]["notes"]
    assert any("lodgeit-rounding-1.0 rules 3, 5 and 7" in n for n in notes), notes


def test_advisory_degrades_never_500(monkeypatch):
    """A failure inside the rounding-advisory append must degrade to the
    un-appended block, never a 500 (missing sentence = defect; dead route =
    outage)."""
    import api.lib.advisory_boundary as ab

    def _boom(_uri):
        raise RuntimeError("simulated metadata failure")

    # Force the lookup used by _append_rounding_advisory to raise.
    monkeypatch.setattr(
        "api.lib.calculator_metadata.rounding_advisory_for", _boom
    )
    block = ab.advisory_block(
        "AU",
        manifest_rate_table_uris=["urn:sbrm:rate:fbt:fy2026:benchmark-interest"],
        calculator_uri="urn:sbrm:calculator:fbt:expense-payment",
    )
    # Degraded: a valid advisory block with a non-empty disclaimer, no crash.
    assert block["disclaimer"]
    assert isinstance(block["registered_agent_required"], bool)
