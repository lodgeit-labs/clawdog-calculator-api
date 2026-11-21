"""D95 (Fable wire-repro 2026-11-21): the Div 7A route must refuse a repayment
whose date falls outside the income year named by the period URI.

Live defect. POST ``/v1/calculators/div7a/at/urn:sbrm:period:div7a:fy2025``
with the body

    {"amalgamated_base": 70000, "loan_term_years": 7,
     "loan_origination_date": "2024-06-01",
     "income_year_start_date": "2024-07-01",
     "repayments": [{"amount": 13801.18, "date": "2023-12-31"}]}

returned HTTP 200 with ``total_repayments="0.00"`` and
``shortfall="13801.18"``. The engine filters repayments to the income year and
drops the rest without a refusal and without any echo, so a mistyped year
produces a false shortfall and a false deemed dividend under §109E(1) —
silently. (2023-12-31 is FY2024: outside FY2025, which runs 2024-07-01 to
2025-06-30.)

Gateway fix (this PR): every repayment date must fall inside the period's
income year, 1 July to 30 June inclusive, derived from the period URI. Each
offending repayment becomes one 422 ``detail[]`` entry with
``type="repayment_outside_income_year"`` and
``loc=["body","repayments",<index>,"date"]``. A date in neither declared
format (ISO YYYY-MM-DD or AU dd/mm/yyyy) is refused with the same treatment.

Binary-failure assertions:
  1. Fable's exact payload → 422 at index 0.
  2. 2025-07-01 on fy2025 (first day of the NEXT income year) → 422.
  3. 2024-07-01 and 2025-06-30 (the two boundary days) → 200.
  4. Two bad dates among three repayments → exactly two detail entries, at
     the right indexes, in input order.
  5. dd/mm/yyyy inside the year → 200.
  6. An unparseable date → 422 whose msg says the format is not accepted.
  7. MCP ``tools/call`` → ``isError`` with the same body.
  8. The three ATO-anchored FY2025 requests still return 6139.00, 5535.48 and
     5532.16 — the guard refuses nothing that is in-year.
  9. The D94 income_year_start_date refusal is reported first and alone when
     both faults are present.
 10. The engine is never dispatched when a repayment is refused.
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
    REFUSAL_REPAYMENT_OUTSIDE_INCOME_YEAR,
    expected_income_year_bounds,
    repayment_outside_income_year_errors,
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
    "repayments": [{"amount": 13801.18, "date": "2023-12-31"}],
}

ENGINE_200_NO_REPAYMENTS = {
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

# The engine's own 200 body once the (in-year) repayments are aggregated. The
# gateway does not rewrite these fields; the values are the ATO-anchored ones.
ENGINE_200_WITH_REPAYMENT = dict(
    ENGINE_200_NO_REPAYMENTS,
    total_repayments="13801.18",
    shortfall="0.00",
    is_complying=True,
    deemed_dividend="0.00",
    interest_accrued="5535.48",
)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # The 200-path tests build the manifest from the repo's committed rate
    # tables (same fixture discipline as test_d77 / test_d94).
    monkeypatch.setenv("LODGEIT_FBT_REPO", _REPO_RATE_ROOT)
    with TestClient(app) as tc:
        yield tc


@pytest.fixture
def engine() -> Iterator[AsyncMock]:
    """Mock the engine boundary; yields the mock so tests can assert whether
    a dispatch happened at all."""
    mock = AsyncMock(return_value=ENGINE_200_WITH_REPAYMENT)
    with patch("api.routes.calculators.PrologClient.div7a_at", mock):
        yield mock


def _assert_repayment_422(
    resp,
    *,
    expected_indexes: list[int],
    expected_dates: list[str],
    year_start: str = "2024-07-01",
    year_end: str = "2025-06-30",
) -> list[dict]:
    """The standard 422 shape: detail[] with one entry per offending repayment."""
    assert resp.status_code == 422, resp.text
    body = resp.json()
    detail = body["detail"]
    assert isinstance(detail, list), detail
    assert len(detail) == len(expected_indexes), detail
    for err, index, raw in zip(detail, expected_indexes, expected_dates, strict=True):
        assert err["type"] == REFUSAL_REPAYMENT_OUTSIDE_INCOME_YEAR, err
        assert err["loc"] == ["body", "repayments", index, "date"], err
        msg = err["msg"]
        assert raw in msg, msg
        assert year_start in msg, msg
        assert year_end in msg, msg
    return detail


# ---------------------------------------------------------------------------
# 1. Fable's exact payload → 422 at index 0.
# ---------------------------------------------------------------------------


def test_fable_repayment_2023_12_31_on_fy2025_returns_422_at_index_0(
    client: TestClient, engine: AsyncMock
) -> None:
    """The live-reproduced payload is refused instead of being dropped by the
    engine's income-year filter and answered with a false shortfall."""
    resp = client.post(FY2025_URL, json=FABLE_BODY)
    _assert_repayment_422(
        resp, expected_indexes=[0], expected_dates=["2023-12-31"]
    )
    # Refused at the gateway: the engine is never asked.
    engine.assert_not_awaited()


# ---------------------------------------------------------------------------
# 2. The day after the income year ends → 422.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_date",
    [
        "2025-07-01",  # first day of the NEXT income year
        "2024-06-30",  # last day of the PREVIOUS income year
        "2023-12-31",  # Fable's mistyped year
        "2026-06-30",  # a year and a day past the end
    ],
)
def test_repayment_outside_fy2025_returns_422(
    client: TestClient, engine: AsyncMock, bad_date: str
) -> None:
    body = dict(
        FABLE_BODY, repayments=[{"amount": 13801.18, "date": bad_date}]
    )
    resp = client.post(FY2025_URL, json=body)
    _assert_repayment_422(resp, expected_indexes=[0], expected_dates=[bad_date])
    engine.assert_not_awaited()


def test_repayment_outside_fy2026_returns_422_naming_fy2026_bounds(
    client: TestClient, engine: AsyncMock
) -> None:
    body = {
        "amalgamated_base": 70000,
        "loan_term_years": 7,
        "loan_origination_date": "2025-06-01",
        "income_year_start_date": "2025-07-01",
        "repayments": [{"amount": 13615.68, "date": "2024-12-31"}],
    }
    resp = client.post(FY2026_URL, json=body)
    _assert_repayment_422(
        resp,
        expected_indexes=[0],
        expected_dates=["2024-12-31"],
        year_start="2025-07-01",
        year_end="2026-06-30",
    )
    engine.assert_not_awaited()


# ---------------------------------------------------------------------------
# 3. The two boundary days are inside the year → 200.
# ---------------------------------------------------------------------------


def test_boundary_days_2024_07_01_and_2025_06_30_return_200(
    client: TestClient
) -> None:
    body = dict(
        FABLE_BODY,
        repayments=[
            {"amount": 6900.59, "date": "2024-07-01"},
            {"amount": 6900.59, "date": "2025-06-30"},
        ],
    )
    with patch(
        "api.routes.calculators.PrologClient.div7a_at",
        new_callable=AsyncMock,
        return_value=ENGINE_200_WITH_REPAYMENT,
    ) as engine:
        resp = client.post(FY2025_URL, json=body)
    assert resp.status_code == 200, resp.text
    engine.assert_awaited_once()
    forwarded = engine.await_args.args[1]
    assert [r["date"] for r in forwarded["repayments"]] == [
        "2024-07-01",
        "2025-06-30",
    ]


# ---------------------------------------------------------------------------
# 4. Several offenders → one detail entry each, in input order.
# ---------------------------------------------------------------------------


def test_two_bad_dates_among_three_repayments_yield_two_detail_entries(
    client: TestClient, engine: AsyncMock
) -> None:
    body = dict(
        FABLE_BODY,
        repayments=[
            {"amount": 13801.18, "date": "2023-12-31"},  # bad  -> index 0
            {"amount": 13801.18, "date": "2025-01-15"},  # good -> index 1
            {"amount": 13801.18, "date": "2025-07-01"},  # bad  -> index 2
        ],
    )
    resp = client.post(FY2025_URL, json=body)
    _assert_repayment_422(
        resp,
        expected_indexes=[0, 2],
        expected_dates=["2023-12-31", "2025-07-01"],
    )
    engine.assert_not_awaited()


def test_every_repayment_bad_yields_one_entry_per_repayment(
    client: TestClient, engine: AsyncMock
) -> None:
    body = dict(
        FABLE_BODY,
        repayments=[
            {"amount": 1000.00, "date": "2023-01-01"},
            {"amount": 1000.00, "date": "2023-02-01"},
            {"amount": 1000.00, "date": "2023-03-01"},
            {"amount": 1000.00, "date": "2023-04-01"},
        ],
    )
    resp = client.post(FY2025_URL, json=body)
    _assert_repayment_422(
        resp,
        expected_indexes=[0, 1, 2, 3],
        expected_dates=["2023-01-01", "2023-02-01", "2023-03-01", "2023-04-01"],
    )
    engine.assert_not_awaited()


# ---------------------------------------------------------------------------
# 5. dd/mm/yyyy inside the year → 200 (the field declares both formats).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "au_date", ["31/12/2024", "01/07/2024", "30/06/2025", "1/7/2024"]
)
def test_dd_mm_yyyy_repayment_inside_year_returns_200(
    client: TestClient, au_date: str
) -> None:
    body = dict(
        FABLE_BODY, repayments=[{"amount": 13801.18, "date": au_date}]
    )
    with patch(
        "api.routes.calculators.PrologClient.div7a_at",
        new_callable=AsyncMock,
        return_value=ENGINE_200_WITH_REPAYMENT,
    ) as engine:
        resp = client.post(FY2025_URL, json=body)
    assert resp.status_code == 200, resp.text
    engine.assert_awaited_once()
    # The caller's string is forwarded unchanged; the engine parses both forms.
    assert engine.await_args.args[1]["repayments"][0]["date"] == au_date


def test_dd_mm_yyyy_repayment_outside_year_returns_422(
    client: TestClient, engine: AsyncMock
) -> None:
    body = dict(
        FABLE_BODY, repayments=[{"amount": 13801.18, "date": "31/12/2023"}]
    )
    resp = client.post(FY2025_URL, json=body)
    _assert_repayment_422(
        resp, expected_indexes=[0], expected_dates=["31/12/2023"]
    )
    engine.assert_not_awaited()


# ---------------------------------------------------------------------------
# 6. An unparseable date → 422 whose msg says the format is not accepted.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_date",
    ["31-12-2024", "20241231", "2024/12/31", "31 Dec 2024", "not-a-date", ""],
)
def test_unparseable_repayment_date_returns_422_saying_format_not_accepted(
    client: TestClient, engine: AsyncMock, bad_date: str
) -> None:
    body = dict(
        FABLE_BODY, repayments=[{"amount": 13801.18, "date": bad_date}]
    )
    resp = client.post(FY2025_URL, json=body)
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, list) and len(detail) == 1, detail
    err = detail[0]
    assert err["type"] == REFUSAL_REPAYMENT_OUTSIDE_INCOME_YEAR, err
    assert err["loc"] == ["body", "repayments", 0, "date"], err
    msg = err["msg"]
    assert repr(bad_date) in msg or bad_date in msg, msg
    # The msg must say the format is not accepted, and name both formats.
    assert "not a date this calculator accepts" in msg, msg
    assert "YYYY-MM-DD" in msg and "dd/mm/yyyy" in msg, msg
    # And still name the income year's bounds.
    assert "2024-07-01" in msg and "2025-06-30" in msg, msg
    engine.assert_not_awaited()


def test_impossible_calendar_date_returns_422_as_unparseable(
    client: TestClient, engine: AsyncMock
) -> None:
    """strptime rejects 31 February; the guard reports it as unparseable rather
    than silently accepting a rolled-over date."""
    body = dict(
        FABLE_BODY, repayments=[{"amount": 13801.18, "date": "31/02/2024"}]
    )
    resp = client.post(FY2025_URL, json=body)
    assert resp.status_code == 422, resp.text
    err = resp.json()["detail"][0]
    assert "not a date this calculator accepts" in err["msg"], err
    engine.assert_not_awaited()


# ---------------------------------------------------------------------------
# 7. Both REST route shapes → the same 422; MCP tools/call → isError.
# ---------------------------------------------------------------------------

GENERIC_URL = (
    "/v1/calculators/urn%3Asbrm%3Acalculator%3Adiv7a%3Aat/"
    "urn%3Asbrm%3Aperiod%3Adiv7a%3Afy2025"
)


def test_generic_route_returns_the_same_422(
    client: TestClient, engine: AsyncMock
) -> None:
    """The generic ``/v1/calculators/{calc_uri}/{period_uri}`` route delegates
    to the same handler, so it refuses identically rather than dispatching."""
    resp = client.post(GENERIC_URL, json=FABLE_BODY)
    _assert_repayment_422(
        resp, expected_indexes=[0], expected_dates=["2023-12-31"]
    )
    engine.assert_not_awaited()


def test_mcp_tools_call_outside_year_returns_iserror_with_same_body(
    client: TestClient, engine: AsyncMock
) -> None:
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 95,
            "method": "tools/call",
            "params": {
                "name": "div7a-at",
                "arguments": {**FABLE_BODY, "period_uri": FY2025},
            },
        },
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    assert result.get("isError") is True, result
    text_body = json.loads(result["content"][0]["text"])
    assert text_body["detail"][0]["type"] == REFUSAL_REPAYMENT_OUTSIDE_INCOME_YEAR
    assert text_body["detail"][0]["loc"] == ["body", "repayments", 0, "date"]
    assert "2023-12-31" in text_body["detail"][0]["msg"]
    engine.assert_not_awaited()


# ---------------------------------------------------------------------------
# 8. The three ATO-anchored FY2025 requests are untouched by the guard.
# ---------------------------------------------------------------------------


ATO_ANCHORS = [
    (
        [],
        {"interest_accrued": "6139.00", "statutory_myr": "13801.18"},
    ),
    (
        [{"date": "2024-12-31", "amount": "13801.18"}],
        {"interest_accrued": "5535.48", "shortfall": "0.00"},
    ),
    (
        [
            {"date": "2024-12-31", "amount": "13801.18"},
            {"date": "2025-06-30", "amount": "13801.18"},
        ],
        {"interest_accrued": "5532.16"},
    ),
]


@pytest.mark.parametrize("repayments,anchor", ATO_ANCHORS)
def test_ato_anchored_requests_are_not_refused(
    client: TestClient, repayments: list[dict], anchor: dict
) -> None:
    """The guard refuses only out-of-year dates: the three ATO-anchored
    requests are accepted and their payload forwarded byte-faithfully, so the
    anchored interest figures (6139.00 / 5535.48 / 5532.16) are unaffected."""
    body = {
        "amalgamated_base": 70000,
        "loan_term_years": 7,
        "loan_origination_date": "2024-06-01",
        "income_year_start_date": "2024-07-01",
        "repayments": repayments,
    }
    engine_body = dict(ENGINE_200_NO_REPAYMENTS, **anchor)
    with patch(
        "api.routes.calculators.PrologClient.div7a_at",
        new_callable=AsyncMock,
        return_value=engine_body,
    ) as engine:
        resp = client.post(FY2025_URL, json=body)
    assert resp.status_code == 200, resp.text
    engine.assert_awaited_once()
    forwarded = engine.await_args.args[1]
    # Nothing is dropped, reordered, or rewritten on the way through: the
    # guard only refuses, it never edits the caller's ledger. (The model fills
    # its own defaults — loan_id/allocation_hint — so compare the dates.)
    assert [r["date"] for r in forwarded["repayments"]] == [
        r["date"] for r in repayments
    ]
    for field, value in anchor.items():
        assert resp.json()[field] == value, resp.json()


# ---------------------------------------------------------------------------
# 9. Ordering: the D94 period-mismatch refusal comes first and alone.
# ---------------------------------------------------------------------------


def test_period_mismatch_reported_first_and_alone(
    client: TestClient, engine: AsyncMock
) -> None:
    """Both faults present: only the income_year_start_date refusal is
    returned, so the caller fixes one thing at a time and the reported fault
    is the one the period URI contradicts."""
    body = {
        "amalgamated_base": 70000,
        "loan_term_years": 7,
        "loan_origination_date": "2024-06-01",
        "income_year_start_date": "2025-07-01",  # D94 fault on fy2025
        "repayments": [{"amount": 13801.18, "date": "2023-12-31"}],  # D95 fault
    }
    resp = client.post(FY2025_URL, json=body)
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert len(detail) == 1, detail
    assert detail[0]["type"] == "income_year_period_mismatch", detail
    assert detail[0]["loc"] == ["body", "income_year_start_date"], detail
    engine.assert_not_awaited()


# ---------------------------------------------------------------------------
# 10. Guard unit surface: derivation and the empty/absent cases.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "period_uri,start,end",
    [
        (FY2025, date(2024, 7, 1), date(2025, 6, 30)),
        (FY2026, date(2025, 7, 1), date(2026, 6, 30)),
        ("urn:sbrm:period:div7a:fy2031", date(2030, 7, 1), date(2031, 6, 30)),
    ],
)
def test_income_year_bounds_are_derived_from_period_uri(
    period_uri: str, start: date, end: date
) -> None:
    assert expected_income_year_bounds(period_uri) == (start, end)


@pytest.mark.parametrize(
    "period_uri", ["urn:sbrm:period:hp:unscoped", "urn:sbrm:period:div7a:all"]
)
def test_non_fy_period_has_no_bounds_and_no_repayment_refusal(
    period_uri: str,
) -> None:
    """A period carrying no income year has nothing to assert: the guard stays
    out of the way rather than inventing a rule."""
    assert expected_income_year_bounds(period_uri) is None
    assert repayment_outside_income_year_errors(
        period_uri, ["1900-01-01"]
    ) == []


def test_empty_repayments_yield_no_errors() -> None:
    assert repayment_outside_income_year_errors(FY2025, []) == []


def test_leap_day_is_handled_by_calendar_not_by_month_arithmetic() -> None:
    """FY2028 runs 2027-07-01 to 2028-06-30, so 2028-02-29 is inside it and
    must be accepted. 2025-02-29 does not exist and must be refused as
    unparseable rather than rolled forward to 1 March."""
    assert repayment_outside_income_year_errors(
        "urn:sbrm:period:div7a:fy2028", ["2028-02-29"]
    ) == []
    leap_errors = repayment_outside_income_year_errors(FY2025, ["2025-02-29"])
    assert len(leap_errors) == 1, leap_errors
    assert leap_errors[0]["loc"] == ["body", "repayments", 0, "date"]
