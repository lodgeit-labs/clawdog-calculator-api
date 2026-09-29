"""D60 / HP v1_4 anchors (Fable [CALC] 2026-09-29).

Four LodgeiT "Hire Purchase Detailed" reports (hp/290, hp/264, hp/272, hp/235),
row-level checked by Fable at 240/240 rows byte-identical to
api/engines/hp/schedule.py. This test runs compute_schedule on each fixture's
request block and asserts every published rows[] entry, totals, final_balance
and rate_precision_residual equal the fixture byte-for-byte (no tolerance).

The fixture rows carry the financial columns only (instalment, opening,
interest, payment, closing); the engine's per-row date fields are not part of
the anchor assertion surface, so each engine row is projected onto the fixture
row's key set before the byte comparison.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.engines.hp.schedule import compute_schedule

FIXTURE = Path(__file__).parent / "fixtures" / "hp" / "anchors_v1_4.json"


def _contracts() -> list[dict]:
    return json.load(open(FIXTURE))["contracts"]


def _run(request: dict) -> dict:
    return compute_schedule(
        amount_financed=request["amount_financed"],
        annual_rate_pct=request["annual_rate_pct"],
        term_regular_instalments=request["term_regular_instalments"],
        instalment=request["instalment"],
        timing=request["timing"],
        frequency=request["frequency"],
        begin_date=request["begin_date"],
        contract_form=request["contract_form"],
        balloon=request.get("balloon"),
        fy_end_month=6,
    )


_CONTRACTS = _contracts()


@pytest.mark.parametrize(
    "contract", _CONTRACTS, ids=[c["id"] for c in _CONTRACTS]
)
def test_v1_4_byte_identical(contract: dict) -> None:
    result = _run(contract["request"])
    expected = contract["expected"]

    # Rows: same count, and each fixture row equals the engine row projected
    # onto the fixture's key set — byte-for-byte, no tolerance.
    assert len(result["rows"]) == len(expected["rows"]), (
        f"{contract['id']}: row count {len(result['rows'])} != "
        f"{len(expected['rows'])}"
    )
    for i, (engine_row, fixture_row) in enumerate(
        zip(result["rows"], expected["rows"], strict=True)
    ):
        projected = {k: engine_row[k] for k in fixture_row}
        assert projected == fixture_row, (
            f"{contract['id']} row {i}: {projected} != {fixture_row}"
        )

    assert result["totals"] == expected["totals"], f"{contract['id']}: totals"
    assert result["final_balance"] == expected["final_balance"], (
        f"{contract['id']}: final_balance"
    )
    assert result["rate_precision_residual"] == expected["rate_precision_residual"], (
        f"{contract['id']}: rate_precision_residual"
    )
    assert result["fy_interest"] == expected["fy_interest"], (
        f"{contract['id']}: fy_interest"
    )
