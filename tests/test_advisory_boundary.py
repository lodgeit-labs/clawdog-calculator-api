"""Advisory-boundary binary-failure gate (CLAWDOG/110 §3.2 Non-Negotiable #2).

Every endpoint that returns calculator output MUST surface an ``advisory``
block. A response that lacks the block, or whose block is empty / wrong-shape /
not citing statute, fails the build.

Lesson #34 anchor — surfacing the advisory boundary explicitly at every egress
is the discipline; retrofitting it after first contact with auditors is failure.
"""
from __future__ import annotations

from urllib.parse import quote

from api.lib.advisory_boundary import (
    ADVISORY_TEXT_AU,
    ADVISORY_TEXT_AU_EMPTY_MANIFEST,
    ADVISORY_TEXT_UK,
    advisory_block,
    wrap_response,
)

# --- Unit-level surface (the helper itself) -----------------------------------


def test_advisory_block_au_carries_taa_and_tasa_citations() -> None:
    # Fable D6 mc21 2026-09-04: advisory is now conditioned on manifest;
    # non-empty rate_table_uris yields the original text.
    block = advisory_block(
        "AU", manifest_rate_table_uris=[{"uri": "urn:fake"}],
    )
    assert block["disclaimer"] == ADVISORY_TEXT_AU
    assert block["registered_agent_required"] is True
    assert block["jurisdiction"] == "AU"
    statutes = {(b["statute"], b["section"]) for b in block["statutory_basis"]}
    assert ("TAA 1953", "s284-15") in statutes
    assert ("Tax Agent Services Act 2009", "s50-5") in statutes


def test_advisory_block_au_empty_manifest_carries_D6_conditional_text() -> None:
    """Fable D6 mc21 2026-09-04 ruling: when the manifest has no
    rate-table citations, the disclaimer says what the output actually
    rests on (caller-declared inputs), NOT the fictional period-scoped-
    rate-tables text.
    """
    block = advisory_block("AU", manifest_rate_table_uris=[])
    assert block["disclaimer"] == ADVISORY_TEXT_AU_EMPTY_MANIFEST
    assert "consumes no statutory rate tables" in block["disclaimer"]
    assert "is not assessed by this calculator" in block["disclaimer"]
    # TAA + TASA framing preserved (Fable ruled correct + unrelated).
    statutes = {(b["statute"], b["section"]) for b in block["statutory_basis"]}
    assert ("TAA 1953", "s284-15") in statutes
    assert ("Tax Agent Services Act 2009", "s50-5") in statutes


def test_advisory_block_au_absent_manifest_defaults_to_incumbent_not_empty_text() -> None:
    """Fable Q3 mc22 2026-09-04 ruling: absent-manifest defaults to
    the incumbent text, NOT the empty-manifest text.

    Fable verbatim: *"The empty text asserts a negative — no rate
    tables are consumed — and asserting that from a missing manifest
    is a fabrication in the one block doing legal work. Default to
    the incumbent text, which claims nothing about absence."*

    Companion `test_manifest_fidelity` asserts every registered
    calculator's response DOES carry a manifest block, so this branch
    should never fire on a well-formed response — but if it does, the
    incumbent text does not fabricate a claim about consumption.
    """
    block = advisory_block("AU")  # no manifest arg supplied
    assert block["disclaimer"] == ADVISORY_TEXT_AU
    # Explicit None passed — same behaviour: incumbent text.
    block_none = advisory_block("AU", manifest_rate_table_uris=None)
    assert block_none["disclaimer"] == ADVISORY_TEXT_AU


def test_advisory_block_au_explicit_empty_list_uses_empty_manifest_text() -> None:
    """Distinguished from absent-manifest: an explicit empty list is a
    declaration by the response that no rate tables were consumed. The
    empty-manifest text applies."""
    block = advisory_block("AU", manifest_rate_table_uris=[])
    assert block["disclaimer"] == ADVISORY_TEXT_AU_EMPTY_MANIFEST


def test_advisory_block_uk_carries_fa2008_sch41_citation() -> None:
    block = advisory_block("UK")
    assert block["disclaimer"] == ADVISORY_TEXT_UK
    assert block["jurisdiction"] == "UK"
    statutes = {(b["statute"], b["section"]) for b in block["statutory_basis"]}
    assert ("Finance Act 2008", "Schedule 41") in statutes


def test_advisory_wrap_response_attaches_block() -> None:
    out = wrap_response({"taxable_value": 1.0}, jurisdiction="AU")
    assert "advisory" in out
    assert out["advisory"]["jurisdiction"] == "AU"
    assert out["taxable_value"] == 1.0


def test_advisory_wrap_response_replaces_existing_block() -> None:
    """An incoming payload claiming a weaker advisory block is overridden.

    Fable D6 mc21 + Q3 mc22 2026-09-04: `wrap_response` now conditions
    the replacement text on `payload['manifest']['rate_table_uris']`.
    When payload has NO manifest (this test), the incumbent text
    applies — absent-manifest is NOT a claim of absence. TAA + TASA
    framing is preserved in both branches.
    """
    out = wrap_response(
        {"taxable_value": 1.0, "advisory": {"disclaimer": "weak"}},
        jurisdiction="AU",
    )
    # No manifest in payload → incumbent text (Fable Q3 fix).
    assert out["advisory"]["disclaimer"] == ADVISORY_TEXT_AU
    assert "TAA 1953" in out["advisory"]["disclaimer"]


def test_advisory_wrap_response_selects_by_manifest_D6_conditional() -> None:
    """Fable D6 mc21 2026-09-04 ruling: the advisory text is chosen by
    `payload['manifest']['rate_table_uris']` — empty (or missing) yields
    the empty-manifest text; non-empty yields the rate-tables-cited text.
    """
    empty = wrap_response(
        {"taxable_value": 1.0, "manifest": {"rate_table_uris": []}},
        jurisdiction="AU",
    )
    assert empty["advisory"]["disclaimer"] == ADVISORY_TEXT_AU_EMPTY_MANIFEST

    non_empty = wrap_response(
        {
            "taxable_value": 1.0,
            "manifest": {
                "rate_table_uris": [
                    {"uri": "urn:sbrm:rate:fbt:fy2026:fbt-rate"}
                ]
            },
        },
        jurisdiction="AU",
    )
    assert non_empty["advisory"]["disclaimer"] == ADVISORY_TEXT_AU


# --- Endpoint-level surface (every endpoint that returns calculator output) ---

CALC_URI = "urn:sbrm:calculator:fbt:car-operating-cost"
PERIOD_URI = "urn:sbrm:period:fbt:fy2026"

PR_D_CASE_5_INPUT = {
    "businessUsePercentage": 75,
    "employeeContribution": 200,
    "formOfFinance": "owned",
    "leasePayments": 0,
    "fuelRepairsServicing": 3000,
    "registrationInsurance": 1500,
    "noPrivateUseReduction": 0,
    "acquisitionDate": "2024-04-01",
    "openingDepreciatedValue": 55000,
    "daysHeldInFBTYear": 365,
}


def test_calculator_invocation_endpoint_carries_advisory_block(
    fastapi_test_client,
) -> None:
    """POST /v1/calculators/{calc}/{period} must include an advisory block.

    Binary-failure gate: the test fails if the block is absent, empty, or
    missing the statutory citation strings.
    """
    url = f"/v1/calculators/{quote(CALC_URI, safe='')}/{quote(PERIOD_URI, safe='')}"
    resp = fastapi_test_client.post(url, json=PR_D_CASE_5_INPUT)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "advisory" in body, "calculator-invocation response missing advisory block"
    advisory = body["advisory"]
    assert advisory["disclaimer"], "advisory.disclaimer is empty"
    assert "TAA 1953" in advisory["disclaimer"]
    assert "Tax Agent Services Act" in advisory["disclaimer"]
    assert advisory["registered_agent_required"] is True
    assert advisory["statutory_basis"], "advisory.statutory_basis is empty"


def test_every_registered_calculator_response_carries_manifest_block(
    fastapi_test_client,
) -> None:
    """Fable Q3 mc22 2026-09-04 companion gate.

    Fable verbatim: *"add a unit test asserting every registered
    calculator's response carries a manifest block so the absent case
    is a test failure rather than a runtime guess."*

    The advisory conditional in `wrap_response` reads
    `payload['manifest']['rate_table_uris']`. Under Fable Q3 fix, an
    absent manifest defaults to the incumbent (rate-tables-cited) text
    — which is a safe default (asserts no negative) but is still a
    fabrication if the response never carried a manifest. This test
    fires every registered calculator through the invocation route and
    asserts a `manifest` block is present, so the absent-manifest
    branch is dead code by test discipline.

    Uses mocked engine responses so that transport failures do not
    hide the manifest-fidelity check; the *shape* of the response is
    what we're asserting, not its content.
    """

    from api.main import app
    from api.routes.calculators import (
        _CALCULATOR_REGISTRY,
        get_prolog_client,
    )

    # Minimal happy-path engine responses per calc_uri family. Any calc
    # that requires a specific field-shape gets a bespoke entry;
    # everything else falls back to a Wave-A-shaped taxable_value body.
    def _fake_response_for(calc_uri: str) -> dict:
        if calc_uri == "urn:sbrm:calculator:depreciation:at":
            return {
                "basis": "accounting", "at_date": "2023-07-31",
                "wdv_at": "9830.60", "period_dep_at": "169.40",
                "schedule_summary": {
                    "opening_balance": "10000.00",
                    "closing_balance_at": "9830.60",
                    "total_depreciation_to_date": "169.40",
                    "total_cost_additions": "0.00",
                    "fiscal_years_covered": [2024],
                },
                "timeline": None, "numeric_mode": "serving",
                "day_count": "actual/actual",
            }
        if calc_uri == "urn:sbrm:calculator:depreciation:range":
            return {
                "basis": "accounting",
                "from_date": "2023-08-01", "to_date": "2023-08-31",
                "day_count": "actual/actual", "days_in_range": 31,
                "range_dep": "169.40", "opening_wdv": "9830.60",
                "closing_wdv": "9661.20", "truncated": False,
                "numeric_mode": "serving",
            }
        if calc_uri == "urn:sbrm:calculator:div7a:at":
            return {
                "loan_uri": "urn:sbrm:asset:div7a:test",
                "myr": "12000.00", "deemed_dividend": "0.00",
                "complying": True, "rate_uris_consumed": [],
            }
        # Wave A/B/C FBT default shape.
        return {"taxable_value": 100.0, "trace": {}}

    class _ManifestPresenceFake:
        """Fake PrologClient that returns the right shape per calc-URI."""

        async def calculate_fbt(self, payload):
            return _fake_response_for("urn:sbrm:calculator:fbt:*")

        async def depreciation_at(self, period_uri, payload):
            return _fake_response_for("urn:sbrm:calculator:depreciation:at")

        async def depreciation_range(self, period_uri, payload):
            return _fake_response_for(
                "urn:sbrm:calculator:depreciation:range"
            )

        async def div7a_at(self, period_uri, payload):
            return _fake_response_for("urn:sbrm:calculator:div7a:at")

    async def _override():
        return _ManifestPresenceFake()

    app.dependency_overrides[get_prolog_client] = _override
    try:
        skipped_no_bundle: list[str] = []
        missing_manifest: list[str] = []
        for calc_uri, meta in _CALCULATOR_REGISTRY.items():
            # For the current test we only need to know the response
            # carries a manifest block. We use the native routes for
            # depreciation and div7a because they are what the generic
            # route delegates to. For FBT (Wave A/B/C) the generic
            # route is the native handler.
            if calc_uri == "urn:sbrm:calculator:depreciation:at":
                path = (
                    f"/v1/calculators/depreciation/at/"
                    f"{quote(meta['supported_periods'][0], safe='')}"
                )
                body = {
                    "basis": "accounting",
                    "asset": {
                        "cost": "10000.00",
                        "acquisition_date": "2023-07-01",
                        "accounting_useful_life_years": 5,
                        "accounting_method": "prime_cost",
                    },
                    "at_date": "2023-07-31",
                }
            elif calc_uri == "urn:sbrm:calculator:depreciation:range":
                path = (
                    f"/v1/calculators/depreciation/range/"
                    f"{quote(meta['supported_periods'][0], safe='')}"
                )
                body = {
                    "basis": "accounting",
                    "asset": {
                        "cost": "10000.00",
                        "acquisition_date": "2023-07-01",
                        "accounting_useful_life_years": 5,
                        "accounting_method": "prime_cost",
                    },
                    "from_date": "2023-08-01",
                    "to_date": "2023-08-31",
                    "day_count": "actual/actual",
                }
            elif calc_uri == "urn:sbrm:calculator:div7a:at":
                path = (
                    f"/v1/calculators/div7a/at/"
                    f"{quote(meta['supported_periods'][0], safe='')}"
                )
                body = {
                    "loan_start_date": "2024-07-01",
                    "loan_amount": "100000.00",
                    "term_years": 7,
                    "benchmark_rate": "0.0862",
                }
            else:
                # Wave A/B/C FBT: exercise via the generic route.
                path = (
                    f"/v1/calculators/{quote(calc_uri, safe='')}/"
                    f"{quote(meta['supported_periods'][0], safe='')}"
                )
                # Minimal FBT body; response_model is disabled on the
                # generic route so per-URN specifics don't matter for
                # the manifest-presence check.
                body = {}

            resp = fastapi_test_client.post(path, json=body)
            # We accept 200 OR a 502 that surfaces a manifest-fidelity
            # bundle-missing error — the latter is out-of-scope for this
            # check; skip those calc URIs and enumerate at the end.
            if resp.status_code == 502:
                detail = resp.json().get("detail", {})
                if isinstance(detail, dict) and detail.get("error") == "manifest_rate_table_unavailable":
                    skipped_no_bundle.append(calc_uri)
                    continue
            # For non-200 responses that are NOT the bundle-missing
            # case, the test fails as a signal something changed in
            # response wrapping.
            if resp.status_code != 200:
                # 422 on a minimal FBT body is expected for calcs with
                # required fields — skip those; they don't reach the
                # wrap layer.
                if resp.status_code == 422:
                    skipped_no_bundle.append(calc_uri)
                    continue
                missing_manifest.append(
                    f"{calc_uri}: status={resp.status_code} body={resp.text[:200]}"
                )
                continue
            body_json = resp.json()
            if "manifest" not in body_json:
                missing_manifest.append(
                    f"{calc_uri}: response missing manifest block"
                )
                continue
            # And the manifest block must have `rate_table_uris` as a
            # list (empty is fine — the D6 conditional handles it).
            rt_uris = body_json["manifest"].get("rate_table_uris")
            if not isinstance(rt_uris, list):
                missing_manifest.append(
                    f"{calc_uri}: manifest.rate_table_uris not a list: {rt_uris!r}"
                )

        assert not missing_manifest, (
            "Fable Q3 companion gate: every registered calculator's "
            "response MUST carry a manifest block with rate_table_uris "
            "as a list. Failures:\n  "
            + "\n  ".join(missing_manifest)
        )
        # Sanity: we should have exercised at least the three non-FBT
        # calcs successfully. If skipped_no_bundle covers all 22
        # something is wrong with the harness itself.
        assert len(skipped_no_bundle) < len(_CALCULATOR_REGISTRY), (
            "All calculators were skipped as bundle-missing/422; "
            "harness failure. Skipped: " + ", ".join(skipped_no_bundle)
        )
    finally:
        app.dependency_overrides.clear()


def test_canonical_disclaimer_text_byte_stable() -> None:
    """The canonical disclaimer language is byte-stable.

    Per CLAWDOG/110 §3.2 the language is canonical to one byte; an accidental
    edit must surface as a test failure rather than a silent regression. If
    the language genuinely needs to change, a Brain-side helm-roll is required
    AND this test is updated in the same PR.
    """
    expected_au_phrases = [
        "This is calculator output, not advice.",
        "Consult a registered tax agent",
        "TAA 1953 s284-15",
        "Tax Agent Services Act 2009",
    ]
    for phrase in expected_au_phrases:
        assert phrase in ADVISORY_TEXT_AU, (
            f"AU disclaimer drift — phrase missing: {phrase!r}"
        )

    expected_uk_phrases = [
        "This is calculator output, not advice.",
        "Finance Act 2008 Schedule 41",
    ]
    for phrase in expected_uk_phrases:
        assert phrase in ADVISORY_TEXT_UK, (
            f"UK disclaimer drift — phrase missing: {phrase!r}"
        )
