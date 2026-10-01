"""D63 (Fable [CALC] 2026-10-01): a refusal body names the calculator's module.

Before D63 the 400 out-of-cohort refusal (added in D62) carried
``"engine": "engine"`` — a placeholder, because ``map_calculation_error_to_http``
hard-coded the engine name. D63 threads the module name
(fbt / div7a / depreciation / hp) from the route via a single helper
(``_engine_name_for``) into ``engine_name`` so each refusal names the engine
that refused.

Fixtures use the exact error term the engine really emits:

* FBT: the double-wrapped ``calculation_failed`` body captured verbatim from the
  live gateway (POST car-operating-cost, acquisitionDate 2005-07-01 → HTTP 400),
  reproduced byte-for-byte here via ``PrologCalculationError``.
* Div 7A: the ``myr_year_beyond_loan_term`` engine-400 body reused verbatim from
  ``tests/test_d54_engine_refusal_mapping.py``.
"""
from __future__ import annotations

import copy
import json

import pytest

from api.lib.engine_error_mapper import (
    map_calculation_error_to_http,
    map_engine_error_to_http,
)
from api.prolog_client import PrologCalculationError, PrologEngineUnavailable

# ---------------------------------------------------------------------------
# FBT: the out-of-cohort refusal (the D62 body with "engine": "engine").
# ---------------------------------------------------------------------------

# Verbatim term the live FBT engine emits for an out-of-cohort acquisition date:
# the wrapped calculation_failed carrying fbt_year_outside_cohort. This is what
# api.prolog_client raises PrologCalculationError from for the live 200-error
# body.
_LIVE_FBT_COHORT_DETAIL = (
    "days_in_year_lookup/3: Unknown error term: "
    "fbt_year_outside_cohort(fy(fy2006),cohort_period("
    "'urn:sbrm:period:fbt:fy2026')) (FBT year not in the days-in-year-by-fy "
    "cohort (FY2022\u2013FY2030 currently; extend via Brain helm-roll of the "
    "days-in-year-by-fy compound node).)"
)

# The exact 400 refusal body the live gateway returned BEFORE D63 (engine is the
# "engine" placeholder). D63 changes exactly one key: engine -> "fbt".
_PRE_D63_FBT_BODY = {
    "refusal_class": "fbt_year_outside_cohort",
    "engine": "engine",
    "requested_fy": "fy2006",
    "supported_cohort_years": ["fy2022", "fy2030"],
    "message": (
        "The acquisition date resolves to an FBT year outside the "
        "deemed-depreciation day-count cohort covered by the FY2026 rate "
        "table (supported range: ['fy2022', 'fy2030']). Supply an acquisition "
        "date whose chained deemed-DV walk stays within the supported cohort "
        "years."
    ),
}


def _fbt_cohort_exc() -> PrologCalculationError:
    return PrologCalculationError(
        error="unrecognised_engine_error", detail=_LIVE_FBT_COHORT_DETAIL
    )


def test_fbt_cohort_refusal_body_unchanged_except_engine_now_fbt():
    """The out-of-cohort 400 body is exactly as before D63, except engine=fbt.

    Asserts same status, same refusal_class, same every other key; the only
    difference between pre-D63 and post-D63 is engine: "engine" -> "fbt".
    """
    exc = _fbt_cohort_exc()

    # Pre-D63 behaviour (no module threaded): the whole body matches the live
    # capture, engine is the "engine" placeholder.
    before = map_calculation_error_to_http(exc)
    assert before.status_code == 400
    assert before.detail == _PRE_D63_FBT_BODY

    # D63: the route threads engine_name="fbt".
    after = map_calculation_error_to_http(exc, engine_name="fbt")
    assert after.status_code == before.status_code == 400
    expected = copy.deepcopy(_PRE_D63_FBT_BODY)
    expected["engine"] = "fbt"
    assert after.detail == expected
    # Spell out the one-key delta explicitly.
    assert after.detail["engine"] == "fbt"
    assert after.detail["refusal_class"] == before.detail["refusal_class"]
    assert {k: v for k, v in after.detail.items() if k != "engine"} == {
        k: v for k, v in before.detail.items() if k != "engine"
    }


# ---------------------------------------------------------------------------
# Second module: Div 7A.
#
# Div 7A's loan-year refusal (myr_year_beyond_loan_term) does NOT go through
# map_calculation_error_to_http. It arrives as an engine HTTP 400 wrapped in
# PrologEngineUnavailable and is mapped by map_engine_error_to_http (see
# tests/test_d54_engine_refusal_mapping.py::
# test_div7a_typed_refusal_maps_to_400_engine_not_unavailable). The Div 7A
# 200-body calculation-error path raises a direct HTTPException
# (div7a_calculation_error, 422) that bypasses the mapper entirely.
#
# Further, that refusal_class arm preserves the engine's refusal envelope
# verbatim ({detail, refusal_class, refusal_payload}) and emits NO "engine" key
# — so there is no engine field to name "div7a". The engine==div7a assertion is
# therefore skipped per the dispatch. We still assert the two facts that justify
# the skip (correct path shape + absence of an engine key).
# ---------------------------------------------------------------------------


def _div7a_loan_year_refusal_exc() -> PrologEngineUnavailable:
    engine_body = json.dumps(
        {
            "detail": "remaining term n=0 at MYR income year FY2031 ...",
            "refusal_class": "myr_year_beyond_loan_term",
            "refusal_payload": {
                "remaining_term_years": 0,
                "loan_fy": 2023,
                "myr_fy": 2031,
            },
        }
    )
    return PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 400, "body": engine_body},
        engine="div7a",
        url="http://div7a-engine.test/v1/calculators/div7a/at/urn:...",
    )


def test_div7a_loan_year_refusal_path_and_skip():
    """Dispatch second-module check: Div 7A's loan-year refusal does NOT go
    through map_calculation_error_to_http.

    It arrives as an engine HTTP 400 (PrologEngineUnavailable) mapped by
    map_engine_error_to_http, whose refusal_class arm preserves the engine's
    envelope verbatim and emits no "engine" key. We assert those facts, then
    skip the engine=="div7a" assertion because there is no engine field to name.
    """
    exc = _div7a_loan_year_refusal_exc()
    http_exc = map_engine_error_to_http(
        exc, engine_label="div7a_engine_unavailable", engine_name="div7a"
    )
    # Correct path + shape: 400, refusal envelope preserved.
    assert http_exc.status_code == 400
    assert http_exc.detail["refusal_class"] == "myr_year_beyond_loan_term"
    # The refusal envelope carries no "engine" key — nothing for D63 to name.
    assert "engine" not in http_exc.detail
    pytest.skip(
        "Div 7A loan-year refusal takes map_engine_error_to_http (not "
        "map_calculation_error_to_http) and its refusal_class body carries no "
        "'engine' key; no engine field to assert."
    )
