"""D60 (Fable [CALC] 2026-09-29) — HP rule 5 footing.

- The Anton case: totals.interest foots to the rounded rows ("9709.45") and
  totals.rounding_residual carries the cent against the exact total ("0.02").
- Footing invariant on every HP anchor fixture:
      totals.interest == Σ rows[].interest == Σ fy_interest.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from api.engines.hp.schedule import compute_schedule

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "hp" / "anchors_v1_3.json"


def test_anton_case_foots_to_rows_with_residual():
    r = compute_schedule(
        amount_financed="50000.00",
        annual_rate_pct="7.25",
        term_regular_instalments=60,
        instalment="1000.00",
        timing="in_arrears",
        frequency="monthly",
        begin_date="2024-07-01",
        contract_form="hire_purchase",
        balloon=None,
        fy_end_month=6,
    )
    assert r["totals"]["interest"] == "9709.45"
    assert r["totals"]["rounding_residual"] == "0.02"
    assert r["manifest"]["engine_version"] == "hp-schedule-1.1.0"
    assert r["manifest"]["rounding_policy"] == "lodgeit-rounding-1.0"
    # invariant
    sum_rows = sum(Decimal(str(row["interest"])) for row in r["rows"])
    sum_fy = sum(Decimal(v) for v in r["fy_interest"].values())
    assert Decimal(r["totals"]["interest"]) == sum_rows == sum_fy


def _fixtures() -> list[dict]:
    return json.load(open(FIXTURES_PATH))["contracts"]


@pytest.mark.parametrize("contract_idx", [0, 1, 2], ids=lambda i: f"contract{i}")
def test_footing_invariant_every_hp_fixture(contract_idx):
    """totals.interest == Σ rows[].interest == Σ fy_interest for every fixture."""
    c = _fixtures()[contract_idx]
    balloon = None
    if c.get("balloon"):
        balloon = {
            "amount": str(c["balloon"]["amount"]),
            "instalment_number": c["balloon"]["row"],
            "mode": c["balloon"].get("mode", "add"),
        }
    r = compute_schedule(
        amount_financed=str(c["amount"]),
        annual_rate_pct=str(c["rate_pct_stated"]),
        term_regular_instalments=c["term"],
        instalment=str(c["instalment"]),
        timing=c["timing"],
        frequency="monthly",
        begin_date=c["begin"],
        contract_form="hire_purchase",
        balloon=balloon,
        fy_end_month=6,
    )
    total = Decimal(r["totals"]["interest"])
    sum_rows = sum(Decimal(str(row["interest"])) for row in r["rows"])
    sum_fy = sum(Decimal(v) for v in r["fy_interest"].values())
    assert total == sum_rows == sum_fy, (
        f"{c['name']}: footing invariant broken — total={total} "
        f"rows={sum_rows} fy={sum_fy}"
    )
    # residual is a signed cent-scale decimal string, "0.00" when exact.
    assert "rounding_residual" in r["totals"]
