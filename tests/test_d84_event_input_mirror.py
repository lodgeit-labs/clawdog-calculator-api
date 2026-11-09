"""D84 (Fable, verified live 2026-11-09): gateway EventInput mirrors the engine.

The gateway's EventInput previously published `cost_delta` and
`opening_balance_amount`; the engine's `extra="forbid"` EventInput rejects both
with 422 `extra_forbidden`, so EVERY amount-carrying event failed through the
gateway on both /at/ and /range/ since launch.

The fix mirrors the engine field-for-field (`event_type`, `event_date`,
`amount`, `new_useful_life_years`), enforces the engine's conditional rules at
the gateway so a caller error returns the standard gateway 422 (`detail[]` with
`type` + `loc`) rather than an engine passthrough, and forwards `amount` to the
engine as a decimal string.

These tests run both endpoints. Forwarding tests patch the engine client and
assert the EXACT engine body the gateway sends. Validation tests assert the
gateway 422 fires BEFORE any engine call (the engine mock is configured to fail
the test if reached).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.prolog_client import PrologEngineUnavailable

DEP_PERIOD = "urn:sbrm:period:depreciation:unscoped"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _range_url() -> str:
    return f"/v1/calculators/depreciation/range/{quote(DEP_PERIOD, safe='')}"


def _at_url() -> str:
    return f"/v1/calculators/depreciation/at/{quote(DEP_PERIOD, safe='')}"


def _asset() -> dict:
    return {
        "cost": "10000.00",
        "acquisition_date": "2023-07-01",
        "accounting_useful_life_years": 5,
        "accounting_method": "prime_cost",
    }


def _range_body(events: list[dict]) -> dict:
    return {
        "basis": "accounting",
        "asset": _asset(),
        "from_date": "2023-05-01",
        "to_date": "2023-12-31",
        "day_count": "actual/actual",
        "events": events,
    }


def _at_body(events: list[dict]) -> dict:
    return {
        "basis": "accounting",
        "asset": _asset(),
        "at_date": "2023-12-31",
        "day_count": "actual/actual",
        "events": events,
    }


def _ok_range_engine_resp() -> dict:
    # A valid three-term-consistent engine response so the identity gate passes
    # when a forwarding test lets the (patched) engine "answer".
    return {
        "rounding_policy": "lodgeit-rounding-1.0",
        "basis": "accounting",
        "from_date": "2023-05-01",
        "to_date": "2023-12-31",
        "day_count": "actual/actual",
        "days_in_range": 245,
        "range_dep": "1540.81",
        "cost_additions": "2000.00",
        "opening_wdv": "8334.25",
        "closing_wdv": "8793.44",
        "truncated": False,
        "numeric_mode": "serving",
    }


def _ok_at_engine_resp() -> dict:
    return {
        "rounding_policy": "lodgeit-rounding-1.0",
        "basis": "accounting",
        "at_date": "2023-12-31",
        "day_count": "actual/actual",
        "wdv_at": "8793.44",
        "period_dep_at": "1540.81",
    }


# A mock that fails the test if the engine is ever reached (validation tests).
def _engine_must_not_be_called(*_args, **_kwargs):
    raise AssertionError(
        "engine was called but the gateway 422 should have fired first"
    )


# ---------------------------------------------------------------------------
# Forwarding: cost_addition with amount → engine body carries the event
# verbatim with amount as a decimal string.
# ---------------------------------------------------------------------------


def test_range_cost_addition_amount_forwarded_verbatim(client: TestClient) -> None:
    mock = AsyncMock(return_value=_ok_range_engine_resp())
    with patch(
        "api.routes.calculators.PrologClient.depreciation_range", new=mock
    ):
        resp = client.post(
            _range_url(),
            json=_range_body(
                [
                    {
                        "event_type": "cost_addition",
                        "event_date": "2023-10-01",
                        "amount": "2000.00",
                    }
                ]
            ),
        )
    assert resp.status_code == 200, resp.text
    # The gateway forwards (period_uri, payload); assert the engine body.
    assert mock.await_count == 1
    _period, payload = mock.await_args.args
    assert payload["events"] == [
        {
            "event_type": "cost_addition",
            "event_date": "2023-10-01",
            "amount": "2000.00",
        }
    ], payload["events"]
    # amount is a decimal STRING on the wire to the engine (not a float).
    assert isinstance(payload["events"][0]["amount"], str)


def test_at_cost_addition_amount_forwarded_verbatim(client: TestClient) -> None:
    mock = AsyncMock(return_value=_ok_at_engine_resp())
    with patch("api.routes.calculators.PrologClient.depreciation_at", new=mock):
        resp = client.post(
            _at_url(),
            json=_at_body(
                [
                    {
                        "event_type": "cost_addition",
                        "event_date": "2023-10-01",
                        "amount": "2000.00",
                    }
                ]
            ),
        )
    assert resp.status_code == 200, resp.text
    assert mock.await_count == 1
    _period, payload = mock.await_args.args
    assert payload["events"] == [
        {
            "event_type": "cost_addition",
            "event_date": "2023-10-01",
            "amount": "2000.00",
        }
    ], payload["events"]
    assert isinstance(payload["events"][0]["amount"], str)


# ---------------------------------------------------------------------------
# Gateway 422 (conditional rules enforced at the gateway, engine not reached).
# ---------------------------------------------------------------------------


def _assert_gateway_422_loc(resp, expected_type: str, loc_tail) -> None:
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, list), detail
    hits = [
        e
        for e in detail
        if isinstance(e, dict)
        and e.get("type") == expected_type
        and list(e.get("loc", []))[-len(loc_tail):] == list(loc_tail)
    ]
    assert hits, (
        f"expected a {expected_type!r} error at loc tail {loc_tail}; got {detail}"
    )


@pytest.mark.parametrize("url_fn,body_fn", [(_range_url, _range_body), (_at_url, _at_body)])
def test_cost_addition_no_amount_is_gateway_422(client, url_fn, body_fn) -> None:
    with patch(
        "api.routes.calculators.PrologClient.depreciation_range",
        new=AsyncMock(side_effect=_engine_must_not_be_called),
    ), patch(
        "api.routes.calculators.PrologClient.depreciation_at",
        new=AsyncMock(side_effect=_engine_must_not_be_called),
    ):
        resp = client.post(
            url_fn(),
            json=body_fn(
                [{"event_type": "cost_addition", "event_date": "2023-10-01"}]
            ),
        )
    # pydantic model-validator ValueError → 422 value_error at the event index.
    _assert_gateway_422_loc(resp, "value_error", ("events", 0))


@pytest.mark.parametrize("url_fn,body_fn", [(_range_url, _range_body), (_at_url, _at_body)])
def test_useful_life_reassessment_with_amount_is_gateway_422(
    client, url_fn, body_fn
) -> None:
    with patch(
        "api.routes.calculators.PrologClient.depreciation_range",
        new=AsyncMock(side_effect=_engine_must_not_be_called),
    ), patch(
        "api.routes.calculators.PrologClient.depreciation_at",
        new=AsyncMock(side_effect=_engine_must_not_be_called),
    ):
        resp = client.post(
            url_fn(),
            json=body_fn(
                [
                    {
                        "event_type": "useful_life_reassessment",
                        "event_date": "2023-10-01",
                        "new_useful_life_years": 7,
                        "amount": "100.00",
                    }
                ]
            ),
        )
    _assert_gateway_422_loc(resp, "value_error", ("events", 0))


@pytest.mark.parametrize("url_fn,body_fn", [(_range_url, _range_body), (_at_url, _at_body)])
def test_removed_cost_delta_is_extra_forbidden_422(client, url_fn, body_fn) -> None:
    with patch(
        "api.routes.calculators.PrologClient.depreciation_range",
        new=AsyncMock(side_effect=_engine_must_not_be_called),
    ), patch(
        "api.routes.calculators.PrologClient.depreciation_at",
        new=AsyncMock(side_effect=_engine_must_not_be_called),
    ):
        resp = client.post(
            url_fn(),
            json=body_fn(
                [
                    {
                        "event_type": "cost_addition",
                        "event_date": "2023-10-01",
                        "cost_delta": "2000.00",
                    }
                ]
            ),
        )
    _assert_gateway_422_loc(resp, "extra_forbidden", ("events", 0, "cost_delta"))


@pytest.mark.parametrize("url_fn,body_fn", [(_range_url, _range_body), (_at_url, _at_body)])
def test_removed_opening_balance_amount_is_extra_forbidden_422(
    client, url_fn, body_fn
) -> None:
    with patch(
        "api.routes.calculators.PrologClient.depreciation_range",
        new=AsyncMock(side_effect=_engine_must_not_be_called),
    ), patch(
        "api.routes.calculators.PrologClient.depreciation_at",
        new=AsyncMock(side_effect=_engine_must_not_be_called),
    ):
        resp = client.post(
            url_fn(),
            json=body_fn(
                [
                    {
                        "event_type": "opening_balance",
                        "event_date": "2023-07-01",
                        "opening_balance_amount": "5000.00",
                    }
                ]
            ),
        )
    _assert_gateway_422_loc(
        resp, "extra_forbidden", ("events", 0, "opening_balance_amount")
    )


# ---------------------------------------------------------------------------
# Engine 400 range_spans_opening_balance → uniform 400 refusal passthrough.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url_fn,body_fn,client_attr",
    [
        (_range_url, _range_body, "depreciation_range"),
        (_at_url, _at_body, "depreciation_at"),
    ],
)
def test_engine_range_spans_opening_balance_passthrough_400(
    client, url_fn, body_fn, client_attr
) -> None:
    import json as _json

    refusal_body = _json.dumps(
        {
            "refusal_class": "range_spans_opening_balance",
            "refusal_payload": {
                "from_date": "2023-05-01",
                "event_date": "2023-07-01",
                "to_date": "2023-12-31",
            },
        }
    )
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 400, "body": refusal_body},
        engine="depreciation",
        url="http://dep-engine.test",
    )
    with patch(
        f"api.routes.calculators.PrologClient.{client_attr}",
        new=AsyncMock(side_effect=exc),
    ):
        resp = client.post(
            url_fn(),
            json=body_fn(
                [
                    {
                        "event_type": "opening_balance",
                        "event_date": "2023-07-01",
                        "amount": "5000.00",
                    }
                ]
            ),
        )
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["engine"] == "depreciation"
    assert detail["refusal_class"] == "range_spans_opening_balance"
