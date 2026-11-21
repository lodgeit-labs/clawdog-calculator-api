"""D94 (Fable wire-repro 2026-11-21): the Div 7A route must refuse an
``income_year_start_date`` that is not 1 July of the income year named by the
period URI.

Live defect. POST ``/v1/calculators/div7a/at/urn:sbrm:period:div7a:fy2026``
with the body below returned HTTP 200 ``benchmark_rate="0.0837"`` (the
FY2026 rate) and ``statutory_myr="13615.68"`` — but the body's income year was
2024-25 (FY2025). The engine reads the RATE from the period URI and the
REMAINING TERM and INTEREST DAYS from ``income_year_start_date``, so a
mismatched pair silently mixes two income years into one MYR. Nothing refused
it.

Gateway fix (this PR): derive the income-year start from the period URI
(``urn:sbrm:period:div7a:fyYYYY`` → 1 July of ``YYYY-1``) and refuse anything
else with 422 ``income_year_period_mismatch`` before the engine dispatch.

Binary-failure assertions:
  1. Fable's exact mismatched payload → 422 in the standard shape.
  2. A mid-year start ("2024-08-15") on fy2025 → 422 (today: silently snapped
     back to 1 July by the engine's ``enclose()``).
  3. Both matching pairs (fy2025+2024-07-01, fy2026+2025-07-01) → 200 unchanged.
  4. dd/mm/yyyy for a matching date → 200 (the field declares both formats).
  5. MCP ``tools/call`` returns ``isError`` with the same 422 body.
  6. The engine is never dispatched on a mismatch.
  7. The expected year is DERIVED from the period URI, not table-driven.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import date
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.lib.income_year_guard import (
    expected_income_year_start,
    parse_iso_or_au_date,
)
from api.main import app

_REPO_RATE_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rate_tables")

FY2025 = "urn:sbrm:period:div7a:fy2025"
FY2026 = "urn:sbrm:period:div7a:fy2026"
FY2025_URL = f"/v1/calculators/div7a/at/{quote(FY2025, safe='')}"
FY2026_URL = f"/v1/calculators/div7a/at/{quote(FY2026, safe='')}"

# Fable's live-reproduced payload (verbatim), 2026-11-21.
FABLE_BODY = {
    "amalgamated_base": 70000,
    "loan_term_years": 7,
    "loan_origination_date": "2024-06-01",
    "income_year_start_date": "2024-07-01",
    "repayments": [],
}

ENGINE_200_FY2025 = {
    "period_uri": FY2025,
    "amalgamated_base": "70000.00",
    "benchmark_rate": "0.0877",
    "remaining_term_years": 7,
    "statutory_myr": "13801.18",
    "total_repayments": "0.00",
    "shortfall": "13801.18",
    "is_complying": False,
    "deemed_dividend": "13801.18",
    "interest_accrued": "6139.00",
    "rounding_policy": "lodgeit-rounding-1.0",
    "rate_uris_consumed": ["urn:sbrm:rate:div7a:fy2025:benchmark-interest"],
}

ENGINE_200_FY2026 = {
    "period_uri": FY2026,
    "amalgamated_base": "70000.00",
    "benchmark_rate": "0.0837",
    "remaining_term_years": 7,
    "statutory_myr": "13615.68",
    "total_repayments": "0.00",
    "shortfall": "13615.68",
    "is_complying": False,
    "deemed_dividend": "13615.68",
    "interest_accrued": "5859.00",
    "rounding_policy": "lodgeit-rounding-1.0",
    "rate_uris_consumed": ["urn:sbrm:rate:div7a:fy2026:benchmark-interest"],
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # The 200-path tests build the manifest from the repo's committed rate
    # tables (same fixture discipline as test_d77).
    monkeypatch.setenv("LODGEIT_FBT_REPO", _REPO_RATE_ROOT)
    with TestClient(app) as tc:
        yield tc


@pytest.fixture
def engine() -> Iterator[AsyncMock]:
    """Mock the engine boundary; yields the mock so tests can assert whether
    a dispatch happened at all."""
    mock = AsyncMock(return_value=ENGINE_200_FY2025)
    with patch("api.routes.calculators.PrologClient.div7a_at", mock):
        yield mock


def _assert_mismatch_422(resp, *, expected_date: str, period_uri: str) -> dict:
    """The standard 422 shape: detail[] with type/loc/msg."""
    assert resp.status_code == 422, resp.text
    body = resp.json()
    detail = body["detail"]
    assert isinstance(detail, list), detail
    assert len(detail) == 1, detail
    err = detail[0]
    assert err["type"] == "income_year_period_mismatch", err
    assert err["loc"] == ["body", "income_year_start_date"], err
    msg = err["msg"]
    assert expected_date in msg, msg
    assert period_uri in msg, msg
    return err


# ---------------------------------------------------------------------------
# 1. Fable's exact mismatch → 422.
# ---------------------------------------------------------------------------


def test_fable_mismatch_fy2026_with_2024_07_01_returns_422(
    client: TestClient, engine: AsyncMock
) -> None:
    """The live-reproduced payload is refused, not answered with the FY2026
    rate applied to the FY2025 income year."""
    resp = client.post(FY2026_URL, json=FABLE_BODY)
    _assert_mismatch_422(resp, expected_date="2025-07-01", period_uri=FY2026)
    # Refused at the gateway: the engine is never asked.
    engine.assert_not_awaited()


# ---------------------------------------------------------------------------
# 2. A mid-year start → 422 (today the engine silently snaps it to 1 July).
# ---------------------------------------------------------------------------


def test_mid_year_start_2024_08_15_on_fy2025_returns_422(
    client: TestClient, engine: AsyncMock
) -> None:
    body = dict(FABLE_BODY, income_year_start_date="2024-08-15")
    resp = client.post(FY2025_URL, json=body)
    _assert_mismatch_422(resp, expected_date="2024-07-01", period_uri=FY2025)
    engine.assert_not_awaited()


def test_january_start_2025_01_01_on_fy2025_returns_422(
    client: TestClient, engine: AsyncMock
) -> None:
    body = dict(FABLE_BODY, income_year_start_date="2025-01-01")
    resp = client.post(FY2025_URL, json=body)
    _assert_mismatch_422(resp, expected_date="2024-07-01", period_uri=FY2025)
    engine.assert_not_awaited()


def test_unparseable_date_returns_422_naming_expected_date(
    client: TestClient, engine: AsyncMock
) -> None:
    """A value in neither declared format cannot be 1 July of the period's
    income year; it is refused with the same type and names the expected date
    rather than reaching the engine as a bare 400."""
    body = dict(FABLE_BODY, income_year_start_date="01-07-2024")
    resp = client.post(FY2025_URL, json=body)
    err = _assert_mismatch_422(resp, expected_date="2024-07-01", period_uri=FY2025)
    assert "YYYY-MM-DD" in err["msg"] and "dd/mm/yyyy" in err["msg"], err["msg"]
    engine.assert_not_awaited()


# ---------------------------------------------------------------------------
# 3. Both matching pairs → 200, unchanged.
# ---------------------------------------------------------------------------


def test_matching_fy2025_200_unchanged(client: TestClient) -> None:
    with patch(
        "api.routes.calculators.PrologClient.div7a_at",
        new_callable=AsyncMock,
        return_value=ENGINE_200_FY2025,
    ) as engine:
        resp = client.post(FY2025_URL, json=FABLE_BODY)
    assert resp.status_code == 200, resp.text
    engine.assert_awaited_once()
    body = resp.json()
    for key, val in ENGINE_200_FY2025.items():
        assert body.get(key) == val, f"{key}: {body.get(key)!r} != {val!r}"
    assert body["manifest"]["rate_table_uris"][0]["uri"].endswith("fy2025:benchmark-interest")


def test_matching_fy2026_200_unchanged(client: TestClient) -> None:
    body_in = dict(FABLE_BODY, income_year_start_date="2025-07-01")
    with patch(
        "api.routes.calculators.PrologClient.div7a_at",
        new_callable=AsyncMock,
        return_value=ENGINE_200_FY2026,
    ) as engine:
        resp = client.post(FY2026_URL, json=body_in)
    assert resp.status_code == 200, resp.text
    engine.assert_awaited_once()
    body = resp.json()
    for key, val in ENGINE_200_FY2026.items():
        assert body.get(key) == val, f"{key}: {body.get(key)!r} != {val!r}"
    assert body["manifest"]["rate_table_uris"][0]["uri"].endswith("fy2026:benchmark-interest")


# ---------------------------------------------------------------------------
# 4. dd/mm/yyyy for a matching date → 200, forwarded verbatim.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "period_uri,url,start,engine_body",
    [
        (FY2026, FY2026_URL, "01/07/2025", ENGINE_200_FY2026),
        (FY2025, FY2025_URL, "01/07/2024", ENGINE_200_FY2025),
    ],
)
def test_dd_mm_yyyy_matching_date_returns_200(
    client: TestClient,
    period_uri: str,
    url: str,
    start: str,
    engine_body: dict,
) -> None:
    body_in = dict(FABLE_BODY, income_year_start_date=start)
    with patch(
        "api.routes.calculators.PrologClient.div7a_at",
        new_callable=AsyncMock,
        return_value=engine_body,
    ) as engine:
        resp = client.post(url, json=body_in)
    assert resp.status_code == 200, resp.text
    engine.assert_awaited_once()
    # The caller's string is forwarded unchanged; the engine parses both forms.
    forwarded_payload = engine.await_args.args[1]
    assert forwarded_payload["income_year_start_date"] == start


# ---------------------------------------------------------------------------
# 5. MCP tools/call → isError with the same body.
# ---------------------------------------------------------------------------


def test_mcp_tools_call_mismatch_returns_iserror_with_same_body(
    client: TestClient, engine: AsyncMock
) -> None:
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 94,
            "method": "tools/call",
            "params": {
                "name": "div7a-at",
                "arguments": {**FABLE_BODY, "period_uri": FY2026},
            },
        },
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    assert result.get("isError") is True, result
    text_body = json.loads(result["content"][0]["text"])
    assert text_body["detail"][0]["type"] == "income_year_period_mismatch"
    assert text_body["detail"][0]["loc"] == ["body", "income_year_start_date"]
    assert "2025-07-01" in text_body["detail"][0]["msg"]
    assert FY2026 in text_body["detail"][0]["msg"]
    engine.assert_not_awaited()


# ---------------------------------------------------------------------------
# 6. Derivation, not a hard-coded table.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "period_uri,expected",
    [
        (FY2025, date(2024, 7, 1)),
        (FY2026, date(2025, 7, 1)),
        ("urn:sbrm:period:div7a:fy2031", date(2030, 7, 1)),
        ("urn:sbrm:period:div7a:fy1999", date(1998, 7, 1)),
    ],
)
def test_expected_start_is_derived_from_period_uri(period_uri: str, expected: date) -> None:
    assert expected_income_year_start(period_uri) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2024-07-01", date(2024, 7, 1)),
        ("01/07/2024", date(2024, 7, 1)),
        ("1/7/2024", date(2024, 7, 1)),
        ("2024-06-30", date(2024, 6, 30)),
    ],
)
def test_parse_iso_or_au_date_accepts_declared_formats(value: str, expected: date) -> None:
    assert parse_iso_or_au_date(value) == expected


@pytest.mark.parametrize("value", ["01-07-2024", "20240701", "2024/07/01", ""])
def test_parse_iso_or_au_date_rejects_other_formats(value: str) -> None:
    assert parse_iso_or_au_date(value) is None
