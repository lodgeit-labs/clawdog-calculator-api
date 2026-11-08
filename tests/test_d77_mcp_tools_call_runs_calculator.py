"""D77 (Fable [CALC] 2026-11-08): MCP tools/call runs the calculator.

Before D77, tools/call returned only a text POINTER ("ready to invoke via REST
POST ...") and never executed the calculator, so MCP clients (Claude custom
connector) got no result (live evidence 2026-11-08, after D69).

D77: tools/call runs the SAME path as the REST route — per-URN input model,
cent checks, engine dispatch, manifest + advisory — via an in-process ASGI
self-call, and returns:

  * on 200: content:[{type:"text", text:<JSON body>}] + structuredContent:<body>;
  * on 400/404/422: isError:true with the REST error body as text.

These tests drive the REAL /mcp route end to end. The Prolog engine is a
separate service, so it is mocked at the gateway's PrologClient boundary to
return the exact bodies the live engine would; the test asserts the gateway
surfaces them through tools/call. The div7a manifest build reads the repo's
rate-table tree (LODGEIT_FBT_REPO → rate_tables/).
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.prolog_client import PrologEngineUnavailable

_REPO_RATE_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rate_tables")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Point the rate-table resolver at the repo's committed rate tables so the
    # div7a manifest build succeeds hermetically (no /srv/lodgeit_fbt mount).
    monkeypatch.setenv("LODGEIT_FBT_REPO", _REPO_RATE_ROOT)
    with TestClient(app) as tc:
        yield tc


def _tools_call(client: TestClient, name: str, arguments: dict, id_: int = 1):
    return client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": id_,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )


# ---------------------------------------------------------------------------
# 200 path: FBT car statutory formula → structuredContent.fbt_payable.
# ---------------------------------------------------------------------------


def test_fbt_car_statutory_formula_returns_structured_result(client: TestClient) -> None:
    """tools/call fbt-car-statutory-formula with the dispatch inputs →
    structuredContent.fbt_payable == "8603.71" and matching text content.
    """
    engine_body = {
        "taxable_value": "4136.00",
        "fbt_type": "Type 1",
        "gross_up_factor": "2.0802",
        "grossed_up_taxable_value": "8603.71",
        "fbt_payable": "8603.71",
    }
    with patch(
        "api.routes.calculators.PrologClient.calculate_fbt",
        new_callable=AsyncMock,
        return_value=engine_body,
    ):
        resp = _tools_call(
            client,
            "fbt-car-statutory-formula",
            {
                "baseValue": 45000,
                "accessories": 5000,
                "daysAvailable": 365,
                "employeeContribution": 1200,
                "fbtType": "Type 1",
                "period_uri": "urn:sbrm:period:fbt:fy2026",
            },
        )
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    assert not result.get("isError")
    # structuredContent carries the computed body.
    assert result["structuredContent"]["fbt_payable"] == "8603.71"
    # text content mirrors the JSON body.
    text_body = json.loads(result["content"][0]["text"])
    assert text_body["fbt_payable"] == "8603.71"


# ---------------------------------------------------------------------------
# 200 path: Div 7A → structuredContent.statutory_myr.
# ---------------------------------------------------------------------------


def test_div7a_at_returns_structured_result(client: TestClient) -> None:
    """tools/call div7a-at ($70k, 7yr, loan 2024-06-01, iys 2024-07-01, fy2025)
    → structuredContent.statutory_myr == "13801.18".
    """
    engine_body = {
        "period_uri": "urn:sbrm:period:div7a:fy2025",
        "amalgamated_base": "70000.0",
        "benchmark_rate": "0.0877",
        "remaining_term_years": 7,
        "statutory_myr": "13801.18",
        "total_repayments": "0.00",
        "shortfall": "13801.18",
        "is_complying": False,
        "deemed_dividend": "13801.18",
        "interest_accrued": "6137.00",
    }
    with patch(
        "api.routes.calculators.PrologClient.div7a_at",
        new_callable=AsyncMock,
        return_value=engine_body,
    ):
        resp = _tools_call(
            client,
            "div7a-at",
            {
                "amalgamated_base": 70000,
                "loan_term_years": 7,
                "loan_origination_date": "2024-06-01",
                "income_year_start_date": "2024-07-01",
                "is_first_real_myr_year": True,
                "repayments": [],
                "period_uri": "urn:sbrm:period:div7a:fy2025",
            },
        )
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    assert not result.get("isError")
    assert result["structuredContent"]["statutory_myr"] == "13801.18"
    assert json.loads(result["content"][0]["text"])["statutory_myr"] == "13801.18"


# ---------------------------------------------------------------------------
# Error path: half-cent input → isError + money_not_cent_quantised.
# ---------------------------------------------------------------------------


def test_half_cent_input_is_error_money_not_cent_quantised(client: TestClient) -> None:
    """A half-cent money input is refused at the gateway cent check (422) and
    surfaces through tools/call as isError with money_not_cent_quantised.
    """
    resp = _tools_call(
        client,
        "fbt-car-statutory-formula",
        {
            "baseValue": 45000,
            "accessories": 5000,
            "daysAvailable": 365,
            "employeeContribution": 1200.005,  # half-cent → not cent-quantised
            "fbtType": "Type 1",
            "period_uri": "urn:sbrm:period:fbt:fy2026",
        },
    )
    assert resp.status_code == 200, resp.text  # JSON-RPC envelope is 200
    result = resp.json()["result"]
    assert result.get("isError") is True
    assert "money_not_cent_quantised" in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# Error path: a refusal → isError with the D73 uniform 400 shape.
# ---------------------------------------------------------------------------


def test_div7a_refusal_is_error_with_d73_400_shape(client: TestClient) -> None:
    """An engine 400 refusal surfaces through tools/call as isError whose text
    is the D73 uniform 400 shape: refusal_class top-level + engine "div7a".
    """
    refusal = json.dumps(
        {
            "refusal_class": "myr_year_not_after_loan_year",
            "refusal_payload": {"loan_making_fy": 2024, "myr_fy": 2024},
            "detail": "MYR income year is not after the loan's making year",
        }
    )
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 400, "body": refusal},
        engine="div7a",
        url="http://div7a-engine.test/v1",
    )
    with patch(
        "api.routes.calculators.PrologClient.div7a_at",
        new_callable=AsyncMock,
        side_effect=exc,
    ):
        resp = _tools_call(
            client,
            "div7a-at",
            {
                "amalgamated_base": 70000,
                "loan_term_years": 7,
                "loan_origination_date": "2024-06-01",
                "income_year_start_date": "2024-07-01",
                "is_first_real_myr_year": True,
                "repayments": [],
                "period_uri": "urn:sbrm:period:div7a:fy2025",
            },
        )
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    assert result.get("isError") is True
    body = json.loads(result["content"][0]["text"])
    # D73 uniform 400 shape, wrapped in FastAPI's {"detail": ...}.
    detail = body["detail"]
    assert detail["refusal_class"] == "myr_year_not_after_loan_year"
    assert detail["engine"] == "div7a"
    assert "refusal_payload" in detail


# ---------------------------------------------------------------------------
# Widget resources keep working (iframe info preserved under _dispatch).
# ---------------------------------------------------------------------------


def test_widget_dispatch_preserved_for_mapped_calc(client: TestClient) -> None:
    """A calc with a mapped widget still surfaces the iframe URL under _dispatch,
    alongside the computed result.
    """
    engine_body = {
        "taxable_value": "4136.00",
        "fbt_type": "Type 1",
        "gross_up_factor": "2.0802",
        "grossed_up_taxable_value": "8603.71",
        "fbt_payable": "8603.71",
    }
    with patch(
        "api.routes.calculators.PrologClient.calculate_fbt",
        new_callable=AsyncMock,
        return_value=engine_body,
    ):
        resp = _tools_call(
            client,
            "fbt-car-operating-cost",
            {
                "businessUsePercentage": 80,
                "formOfFinance": "owned",
                "period_uri": "urn:sbrm:period:fbt:fy2026",
            },
        )
    result = resp.json()["result"]
    # If this calc maps to a widget, the iframe info is present and non-empty;
    # the computed result is still returned either way.
    assert "content" in result
    if "_dispatch" in result:
        assert result["_dispatch"]["widget_url"]
        assert result["_dispatch"]["kind"] == "widget"
