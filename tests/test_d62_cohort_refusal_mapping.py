"""D62: map the engine refusal term ``fbt_year_outside_cohort`` to a typed 400.

The FBT car-operating-cost chained deemed-DV walk throws
``error(fbt_year_outside_cohort(FY, available_range:[fy2022, fy2030]), _)`` when
an acquisition date resolves to an FBT year the FY2026 day-count cohort does not
cover (rate_tables/.../fbt/lodgeit_au_sbrm/fy2026/days-in-year-by-fy.md). That is
the caller's request, not our fault — so it must surface as a 400, never the 502
``unrecognised_engine_error`` fallthrough (D8a).

Before D62 the bare term (no ``refusal_class``) fell through
``_classify_engine_error_term`` and mapped to 502. Each test below asserts the
surfaced status is a 400 (specifically ≠ 502) carrying
``refusal_class == "fbt_year_outside_cohort"`` with the supported cohort years
named, and that the 502 fallthrough for genuinely-unrecognised terms is
unchanged. Reproduced hermetically from the exact wire shape (the FBT serialiser
emits the refusal as an HTTP 500 whose body is a JSON string).

— ClawDog
"""
from __future__ import annotations

import json

from api.lib.engine_error_mapper import (
    map_calculation_error_to_http,
    map_engine_error_to_http,
)
from api.prolog_client import PrologCalculationError, PrologEngineUnavailable

# --- (d62-b) LIVE production wrapped body → 400, never 502 --------------------
# Captured VERBATIM 2026-09-30 by POSTing car-operating-cost with an
# out-of-cohort acquisitionDate (2005-07-01) against production:
#   https://fbt-calculator-api-8340695160.australia-southeast1.run.app
# The engine wraps fbt_year_outside_cohort inside calculation_failed and carries
# the real term (with the FY + the FY2022–FY2030 prose range) as text.
_LIVE_WRAPPED_COHORT_BODY = (
    '{"error":"unrecognised_engine_error","engine_term":"calculation_failed",'
    '"detail":"days_in_year_lookup/3: Unknown error term: '
    'fbt_year_outside_cohort(fy(fy2006),cohort_period('
    "'urn:sbrm:period:fbt:fy2026'"
    ')) (FBT year not in the days-in-year-by-fy cohort (FY2022\u2013FY2030 '
    'currently; extend via Brain helm-roll of the days-in-year-by-fy compound '
    'node).)"}'
)


def test_fbt_year_outside_cohort_live_wrapped_body_maps_to_400_not_502():
    """D62-b: the production-captured calculation_failed body whose text carries
    fbt_year_outside_cohort(...) MUST classify to 400, never 502."""
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 500, "body": _LIVE_WRAPPED_COHORT_BODY},
        engine="fbt-engine",
        url="http://fbt-engine.test/v1/calculators/fbt/car-operating-cost",
    )
    http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 400, http_exc.detail
    assert http_exc.status_code != 502
    detail = http_exc.detail
    assert isinstance(detail, dict)
    assert detail["refusal_class"] == "fbt_year_outside_cohort"
    # FY parsed out of the wrapped term text (`fy(fy2006)`).
    assert detail["requested_fy"] == "fy2006"
    # Supported range parsed from the prose `FY2022–FY2030`.
    assert detail["supported_cohort_years"] == ["fy2022", "fy2030"]
    assert not str(detail["engine"]).endswith("_unavailable")


# --- (d62-1) engine 500-wrapped refusal → 400, never 502 ---------------------

def test_fbt_year_outside_cohort_maps_to_400_not_502():
    """The FBT serialiser wraps the cohort refusal in an HTTP 500 whose body is
    a JSON string. D62: classify by term → 400 with refusal_class, NOT 502."""
    inner = json.dumps({
        "detail": "chained deemed-DV walk reached FBT year outside cohort",
        "error": "fbt_year_outside_cohort",
        "refusal_payload": {
            "fy": "fy2021",
            "available_range": ["fy2022", "fy2030"],
        },
    })
    exc = PrologEngineUnavailable(
        error_code="engine_http_error",
        detail={"status_code": 500, "body": inner},
        engine="fbt",
        url="http://fbt-engine.test/v1/calculators/fbt/car-operating-cost",
    )
    http_exc = map_engine_error_to_http(exc)
    assert http_exc.status_code == 400, http_exc.detail
    assert http_exc.status_code != 502
    detail = http_exc.detail
    assert isinstance(detail, dict)
    assert detail["refusal_class"] == "fbt_year_outside_cohort"
    # Supported cohort years named, taken from the engine body's available_range.
    assert detail["supported_cohort_years"] == ["fy2022", "fy2030"]
    # 4xx label must not carry the transport-only _unavailable suffix.
    assert not str(detail["engine"]).endswith("_unavailable")


# --- (d62-2) 200-with-error-body path, no available_range → fallback listing --

def test_fbt_year_outside_cohort_via_200_body_maps_to_400():
    """The same classification applies to the 200-with-error path
    (``PrologCalculationError``). When the engine body omits available_range,
    the mapper names the rate-table cohort listing [fy2022, fy2030]."""
    exc = PrologCalculationError(
        error="fbt_year_outside_cohort",
        detail={"fy": "fy2031"},
    )
    http_exc = map_calculation_error_to_http(exc)
    assert http_exc.status_code == 400
    assert http_exc.status_code != 502
    detail = http_exc.detail
    assert detail["refusal_class"] == "fbt_year_outside_cohort"
    assert detail["supported_cohort_years"] == ["fy2022", "fy2030"]
    assert detail["requested_fy"] == "fy2031"


# --- (d62-3) genuinely-unrecognised term still 502 (no regression) -----------

def test_unrecognised_term_still_maps_to_502():
    """D62 must NOT change the 502 fallthrough for terms it does not handle."""
    exc = PrologCalculationError(
        error="some_totally_unknown_term",
        detail={"x": 1},
    )
    http_exc = map_calculation_error_to_http(exc)
    assert http_exc.status_code == 502
    assert http_exc.detail["error"] == "unrecognised_engine_error"
    assert http_exc.detail["engine_term"] == "some_totally_unknown_term"
