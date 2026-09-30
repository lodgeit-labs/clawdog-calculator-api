"""D53c (Fable [CALC] 2026-09-30): smoke-fbt bare-float detection must be a
PARSED check, not a raw-text regex.

Anchor incident: canary 00068-xas failed smoke-fbt 0/20 because the previous
raw-text ``BARE_FLOAT_RE`` matched the ``-1.0`` substring inside the D60
rounding-policy token ``lodgeit-rounding-1.0`` (in the advisory prose sentence,
where it is not quote-adjacent). Every monetary value was a correct decimal
string; the failure was a false positive in the gate.

The replacement parses the body with ``json.loads(body, parse_float=<hook>)``:
the hook fires for every JSON *float number literal* and for nothing else, so a
decimal-string like ``"1234.50"`` or a hyphenated string token like
``"lodgeit-rounding-1.0"`` is never recorded, while a real bare float
``1234.5`` (or ``-1.0``) always is.

Four cases per the dispatch:
  (a) rounding_policy string + advisory prose sentence  -> passes
  (b) "taxable_value": 1234.5  (bare float)             -> fails
  (c) "taxable_value": "1234.50"  (decimal string)      -> passes
  (d) -1.0 as a real JSON number                        -> fails

— ClawDog
"""
from __future__ import annotations

import json

from scripts.smoke_fbt_computed import evaluate, parse_float_literals

# A valid decimal-string trio so trio_ok is never the confound in the
# evaluate()-level assertions; float detection is the variable under test.
_TRIO = {
    "gross_up_factor": "1.8868",
    "grossed_up_taxable_value": "150.94",
    "fbt_payable": "70.94",
}


def _body(**extra) -> dict:
    b = dict(_TRIO)
    b.update(extra)
    return b


# --- parse_float_literals: the core detector -------------------------------

def test_a_rounding_policy_string_and_advisory_prose_records_no_floats():
    """(a) The D60 rounding-policy token + advisory prose must NOT be read as a
    float. This is the exact 00068-xas false-positive shape."""
    raw = json.dumps(_body(
        manifest={"rounding_policy": "lodgeit-rounding-1.0"},
        advisory={"notes": [
            "Rounding: lodgeit-rounding-1.0 rule set applied to all monetary "
            "outputs (eight rules; see publish.html).",
        ]},
    ))
    assert parse_float_literals(raw) == []


def test_b_bare_float_taxable_value_is_recorded():
    """(b) A bare JSON float number literal is recorded."""
    raw = '{"taxable_value": 1234.5}'
    assert parse_float_literals(raw) == ["1234.5"]


def test_c_decimal_string_taxable_value_records_no_floats():
    """(c) A cent-quantised decimal STRING is not a float literal."""
    raw = '{"taxable_value": "1234.50"}'
    assert parse_float_literals(raw) == []


def test_d_negative_one_point_zero_as_real_json_number_is_recorded():
    """(d) ``-1.0`` as a real JSON number (not inside a string) is recorded.

    This is the value the old regex was hunting for; the parsed check still
    catches it when it is a genuine bare float, while ignoring the identical
    substring inside the rounding-policy string (case a)."""
    raw = '{"some_field": -1.0}'
    assert parse_float_literals(raw) == ["-1.0"]


# --- evaluate(): end-to-end gate verdict -----------------------------------

def test_a_evaluate_passes_with_policy_string_and_prose():
    raw = json.dumps(_body(
        manifest={"rounding_policy": "lodgeit-rounding-1.0"},
        advisory={"notes": ["Rounding: lodgeit-rounding-1.0 rule set applied."]},
    ))
    row = evaluate("urn:sbrm:calculator:fbt:board", 200, raw)
    assert row["pass"] is True, row["detail"]


def test_c_evaluate_passes_with_decimal_string_field():
    raw = json.dumps(_body(taxable_value="1234.50"))
    row = evaluate("urn:sbrm:calculator:fbt:board", 200, raw)
    assert row["pass"] is True, row["detail"]


def test_b_evaluate_fails_on_bare_float_field():
    # taxable_value as a real float literal must fail the gate.
    raw = '{"gross_up_factor": "1.8868", "grossed_up_taxable_value": "150.94", ' \
          '"fbt_payable": "70.94", "taxable_value": 1234.5}'
    row = evaluate("urn:sbrm:calculator:fbt:board", 200, raw)
    assert row["pass"] is False
    assert "bare JSON float" in row["detail"]


def test_d_evaluate_fails_on_negative_one_float():
    raw = '{"gross_up_factor": "1.8868", "grossed_up_taxable_value": "150.94", ' \
          '"fbt_payable": "70.94", "some_field": -1.0}'
    row = evaluate("urn:sbrm:calculator:fbt:board", 200, raw)
    assert row["pass"] is False
    assert "bare JSON float" in row["detail"]
