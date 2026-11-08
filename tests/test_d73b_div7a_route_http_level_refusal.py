"""D73b addendum (Fable [CALC] 2026-11-08): the dedicated /div7a/at/ route must
flatten a long engine refusal body to the uniform envelope.

Fable's live probes showed the dedicated Div 7A route returning the OLD shape
(engine_bad_request + engine "div7a_engine", refusal_class buried in a
stringified engine_detail) even though the engine's refusal body was complete,
valid JSON. Root cause: PrologClient.dispatch() stored the engine's HTTP-error
body as ``exc.response.text[:500]`` — a 500-char cap that truncated the longer
Div 7A refusal (its ``refusal_payload.alternatives[...]`` pushes it past 500
chars) mid-JSON, so the gateway mapper's ``_recover_refusal_class`` could not
parse it and the body fell to the bare-400 arm. Depreciation + HP refusals fit
under 500 chars, so they looked correct on the same deploy. The same truncation
produced the mid-word shortening Fable saw in probe 2.

These tests drive the REAL dedicated route end to end with the engine mocked at
the HTTP level (httpx.MockTransport), so ``dispatch()``'s real HTTPStatusError
path — including the body-capture fix — is exercised. Both of Fable's live
bodies are used as fixtures.
"""
from __future__ import annotations

import json
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.prolog_client import PrologClient
from api.routes.calculators import get_prolog_client

_DIV7A_PERIOD = "urn:sbrm:period:div7a:fy2025"
_DIV7A_URL = f"/v1/calculators/div7a/at/{quote(_DIV7A_PERIOD, safe='')}"

# Probe 1: myr_year_not_after_loan_year. Complete, valid-JSON engine refusal
# body whose refusal_payload.alternatives list pushes it well past 500 chars —
# the exact shape Fable's live probe reported.
_PROBE1_INNER = {
    "detail": (
        "MYR income year FY2024 is not after the loan's making year FY2024; "
        "Division 7A requires the first minimum yearly repayment to fall in the "
        "income year AFTER the income year in which the amalgamated loan was "
        "made (s 109E). Shift the loan into the prior income year, or move the "
        "MYR into the 1 income years following the making year."
    ),
    "refusal_class": "myr_year_not_after_loan_year",
    "refusal_payload": {
        "loan_making_fy": 2024,
        "myr_fy": 2024,
        "alternatives": [
            "(a) supply income_year_start_date after 2024-06-30",
            "(b) supply loan_origination_date in the prior income year",
        ],
    },
}
_PROBE1_BODY = json.dumps(_PROBE1_INNER)

# Probe 2: a deliberately longer body (extra prose) to prove the fix holds well
# past the old 500-char cap and no mid-word shortening occurs.
_PROBE2_INNER = {
    "detail": (
        "MYR income year FY2024 is not after the loan's making year FY2024. " * 6
    ).strip(),
    "refusal_class": "myr_year_not_after_loan_year",
    "refusal_payload": {
        "loan_making_fy": 2024,
        "myr_fy": 2024,
        "alternatives": [
            "(a) supply income_year_start_date after 2024-06-30",
            "(b) supply loan_origination_date in the prior income year",
            "(c) confirm the amalgamated base and term with the taxpayer",
        ],
    },
}
_PROBE2_BODY = json.dumps(_PROBE2_INNER)

_VALID_DIV7A_INPUT = {
    "amalgamated_base": 70000,
    "loan_term_years": 7,
    "loan_origination_date": "2024-06-01",
    "income_year_start_date": "2023-07-01",
    "is_first_real_myr_year": True,
    "repayments": [],
}


def _mock_client_returning(status_code: int, body: str) -> PrologClient:
    """A PrologClient whose httpx transport returns one fixed engine response,
    so dispatch()'s real HTTPStatusError path runs against it.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            content=body.encode("utf-8"),
            headers={"content-type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    async_client = httpx.AsyncClient(transport=transport)
    # localhost div7a base URL → _authenticated_headers soft-mode ({} headers),
    # so the test needs no Cloud Run identity.
    return PrologClient(div7a_base_url="http://localhost:9999", client=async_client)


@pytest.fixture
def client_with_engine_400():
    """Factory: mount the app with get_prolog_client overridden to a client
    whose mocked engine returns a given 400 body."""
    created: list[PrologClient] = []

    def make(body: str) -> TestClient:
        pc = _mock_client_returning(400, body)
        created.append(pc)
        app.dependency_overrides[get_prolog_client] = lambda: pc
        return TestClient(app)

    yield make
    app.dependency_overrides.pop(get_prolog_client, None)


@pytest.mark.parametrize(
    "body,label",
    [
        pytest.param(_PROBE1_BODY, "probe1", id="probe1-myr-not-after-loan-year"),
        pytest.param(_PROBE2_BODY, "probe2", id="probe2-longer-body-no-shortening"),
    ],
)
def test_div7a_route_flattens_long_refusal_to_uniform_envelope(
    client_with_engine_400, body: str, label: str
) -> None:
    """The dedicated /div7a/at/ route, with the engine returning a long valid
    JSON 400 refusal, flattens to the uniform envelope: refusal_class at the top
    level + engine "div7a" (never "div7a_engine"), with the full body preserved.
    """
    assert len(body) > 500, "fixture must exceed the historic 500-char cap"
    tc = client_with_engine_400(body)
    resp = tc.post(_DIV7A_URL, json=_VALID_DIV7A_INPUT)
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, dict), detail
    # The two load-bearing assertions.
    assert detail["refusal_class"] == "myr_year_not_after_loan_year"
    assert detail["engine"] == "div7a"
    assert detail["engine"] != "div7a_engine"
    assert not str(detail["engine"]).endswith("_unavailable")
    # refusal_payload recovered intact — including the alternatives list that
    # the old 500-char cap truncated.
    rp = detail["refusal_payload"]
    assert isinstance(rp, dict)
    assert rp.get("alternatives"), rp
    # No mid-word shortening: the last alternative survived whole.
    last_alt = rp["alternatives"][-1]
    assert last_alt.endswith(("year", "taxpayer")), last_alt


def test_div7a_route_full_body_not_truncated_at_500(client_with_engine_400) -> None:
    """Regression guard for the root cause: the engine body captured by
    dispatch() is preserved whole (valid JSON round-trips), not cut at 500.
    """
    tc = client_with_engine_400(_PROBE2_BODY)
    resp = tc.post(_DIV7A_URL, json=_VALID_DIV7A_INPUT)
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    # The message (recovered from the engine body's detail) is the full prose,
    # not a 500-char-truncated fragment.
    assert isinstance(detail.get("message"), str)
    assert len(_PROBE2_BODY) > 500
    # The recovered refusal_payload alternatives are all present (3 in probe 2).
    assert len(detail["refusal_payload"]["alternatives"]) == 3
