"""D65 (Fable [CALC] 2026-10-01): three percentage/count fields are NOT money.

businessUsePercentage, otherwiseDeductiblePercentage and spacesProvided were
cent-quantised Money fields (D56) that rejected sub-cent values with
``money_not_cent_quantised`` (422). They are a percentage, a percentage, and a
count — none is money. D65 restores the pre-D56 plain-number type + bounds and
removes ``x-money``.

The read-only baseline (verified against the live wire + committed openapi.json
at D65 open):

* live ``/openapi.json`` x-money count before D65 = **79**
* D65 removes x-money from 4 property occurrences:
  - businessUsePercentage       (FBTCarOperatingCostInput)        1
  - otherwiseDeductiblePercentage (FBTExpensePayment{,InHouse}Input) 2
  - spacesProvided              (FBTCarParkingActualInput)         1
* expected post-D65 x-money count = 79 - 4 = **75**

Pre-D56 types restored (openapi 42b7eca, 21 Sept):
  businessUsePercentage          number, minimum 0, maximum 100
  otherwiseDeductiblePercentage  number, minimum 0, maximum 100
  spacesProvided                 number, minimum 0 (no maximum)   <-- NOT int;
      git history (a37b2f5) shows the pre-D56 type was ``float``, so number/
      min-0 is restored exactly rather than typing it int.
"""
from __future__ import annotations

import json
import pathlib
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from api.main import app

FBT_PERIOD = "urn:sbrm:period:fbt:fy2026"

# The three D65 non-money fields, by OpenAPI alias.
_THREE_FIELDS = (
    "businessUsePercentage",
    "otherwiseDeductiblePercentage",
    "spacesProvided",
)

# Expected live x-money count AFTER D65 = (pre-D65 count 79) - (4 removed).
# The pre-D65 count is pinned here as the read-only baseline; if the baseline
# shifts, this test fails loudly and the number is re-anchored in the same PR.
_XMONEY_COUNT_BEFORE_D65 = 79
_XMONEY_REMOVED_BY_D65 = 4
_EXPECTED_XMONEY_COUNT = _XMONEY_COUNT_BEFORE_D65 - _XMONEY_REMOVED_BY_D65  # 75


def _fbt_url(calc_uri: str) -> str:
    return f"/v1/calculators/{quote(calc_uri, safe='')}/{quote(FBT_PERIOD, safe='')}"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _live_openapi() -> dict:
    """The committed openapi.json IS the wire shape: the drift gate
    (test_openapi_drift / make openapi-check) proves it byte-equals the live
    app's app.openapi(). Reading the committed file is therefore a wire-shape
    assertion, hermetically."""
    path = pathlib.Path(__file__).resolve().parent.parent / "openapi.json"
    return json.loads(path.read_text())


# --- (i) openapi.json x-money assertions -------------------------------------


def _xmoney_properties(spec: dict) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for sname, sch in spec.get("components", {}).get("schemas", {}).items():
        for pname, pv in (sch.get("properties") or {}).items():
            if isinstance(pv, dict) and pv.get("x-money") is True:
                hits.append((sname, pname))
    return hits


def test_three_fields_carry_no_x_money():
    """None of the three D65 fields carries x-money in any schema."""
    spec = _live_openapi()
    offenders = [
        (sname, pname)
        for (sname, pname) in _xmoney_properties(spec)
        if pname in _THREE_FIELDS
    ]
    assert offenders == [], (
        "x-money still present on D65 non-money fields: " + repr(offenders)
    )


def test_three_fields_restored_number_bounds():
    """Each D65 field is a plain number with the restored pre-D56 bounds."""
    spec = _live_openapi()
    schemas = spec["components"]["schemas"]
    found = {f: [] for f in _THREE_FIELDS}
    for sname, sch in schemas.items():
        for pname, pv in (sch.get("properties") or {}).items():
            if pname in _THREE_FIELDS:
                found[pname].append((sname, pv))
    for field, occurrences in found.items():
        assert occurrences, f"{field} not found in any schema"
        for sname, pv in occurrences:
            assert pv.get("type") == "number", (field, sname, pv)
            assert "x-money" not in pv, (field, sname, pv)
            assert pv.get("minimum") == 0, (field, sname, pv)
            if field in ("businessUsePercentage", "otherwiseDeductiblePercentage"):
                assert pv.get("maximum") == 100, (field, sname, pv)
            if field == "spacesProvided":
                assert "maximum" not in pv, (field, sname, pv)


def test_total_x_money_count_equals_expected():
    """The total x-money property count equals the pre-D65 baseline minus the
    4 occurrences D65 removes."""
    spec = _live_openapi()
    count = len(_xmoney_properties(spec))
    assert count == _EXPECTED_XMONEY_COUNT, (
        f"x-money count={count}; expected {_EXPECTED_XMONEY_COUNT} "
        f"(= {_XMONEY_COUNT_BEFORE_D65} - {_XMONEY_REMOVED_BY_D65})"
    )


# --- (ii) a 3-decimal percentage no longer trips money_not_cent_quantised ----

# One request per percentage field with a 3-decimal value. We assert ONLY that
# no money_not_cent_quantised error is raised (not the engine's result): the
# field is no longer cent-quantised, so a 3-decimal percentage is legal input.
_PERCENT_CASES = [
    (
        "urn:sbrm:calculator:fbt:car-operating-cost",
        "businessUsePercentage",
        {
            "businessUsePercentage": 33.333,
            "formOfFinance": "owned",
            "acquisitionDate": "2022-07-01",
            "acquisitionCost": 20000,
        },
    ),
    (
        "urn:sbrm:calculator:fbt:expense-payment",
        "otherwiseDeductiblePercentage",
        {
            "expenseValue": 2000,
            "otherwiseDeductiblePercentage": 33.333,
            "fbtType": "Type 1",
        },
    ),
]


@pytest.mark.parametrize(
    "calc_uri,alias,body",
    _PERCENT_CASES,
    ids=[c[1] for c in _PERCENT_CASES],
)
def test_three_decimal_percentage_not_cent_refused(
    fastapi_test_client, calc_uri, alias, body
):
    resp = fastapi_test_client.post(_fbt_url(calc_uri), json=body)
    # The field is no longer money, so a sub-cent percentage must NOT trip the
    # cent-quantisation validator. Assert that specific error is absent; do not
    # assert the engine's computed result.
    detail = resp.json().get("detail")
    cent_errors = []
    if isinstance(detail, list):
        cent_errors = [
            e
            for e in detail
            if isinstance(e, dict) and e.get("type") == "money_not_cent_quantised"
        ]
    assert not cent_errors, (
        f"{alias}=33.333 wrongly raised money_not_cent_quantised: {cent_errors}"
    )
