"""D60 (Fable [CALC] 2026-09-29) — gateway manifest merge + advisory append.

(a) build_manifest copies a top-level engine rounding_policy into
    manifest.rounding_policy; when absent, the key is omitted (the gateway
    never supplies a default).
(b) advisory_block appends the per-calculator rounding advisory sentence when
    the calculator declares one in calculator_metadata.json.
"""
from __future__ import annotations

from pathlib import Path

from api.lib.advisory_boundary import advisory_block
from api.manifest_fidelity import build_manifest

_RATE_URI = "urn:sbrm:rate:fbt:fy2026:benchmark-interest"


def test_build_manifest_copies_engine_rounding_policy(rate_table_fixture: Path):
    m = build_manifest(
        [_RATE_URI], rate_table_fixture, rounding_policy="lodgeit-rounding-1.0"
    )
    assert m["rounding_policy"] == "lodgeit-rounding-1.0"


def test_build_manifest_omits_rounding_policy_when_absent(rate_table_fixture: Path):
    m = build_manifest([_RATE_URI], rate_table_fixture)  # engine emitted none
    assert "rounding_policy" not in m


def test_advisory_appends_fbt_rounding_sentence():
    block = advisory_block(
        "AU",
        manifest_rate_table_uris=[_RATE_URI],
        calculator_uri="urn:sbrm:calculator:fbt:expense-payment",
    )
    assert "lodgeit-rounding-1.0" in block["disclaimer"]
    assert "single-figure calculator" in block["disclaimer"]


def test_advisory_appends_hp_rounding_sentence():
    block = advisory_block(
        "AU",
        manifest_rate_table_uris=[],
        calculator_uri="urn:sbrm:calculator:hp:schedule",
    )
    assert "lodgeit-rounding-1.0 rules 3, 5 and 7" in block["disclaimer"]
    assert "rate_precision_residual" in block["disclaimer"]


def test_advisory_no_rounding_sentence_when_calculator_unknown():
    block = advisory_block("AU", manifest_rate_table_uris=[_RATE_URI])
    assert "lodgeit-rounding-1.0" not in block["disclaimer"]
