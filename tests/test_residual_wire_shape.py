"""Wire-shape gate for FBT Residual + FBT Residual In-House.

Closes the class of defect surfaced by Waqas Awan's Microsoft-path
proof-of-concept on 2026-07-05 (screenshot surfaced 2026-07-07 09:11 UTC).

**The defect.** Pre-mc01-2026-07-07 the ``_ResidualBaseInput`` Pydantic model
accepted ``gstInclusiveValue`` as the alias for its primary monetary input,
which flowed through the invoke bridge at ``api/routes/calculators.py:519``
as engine-payload key ``gst_inclusive_value``. The Prolog engine predicate at
``LodgeiT_FBT/FBT_Engine.pl:3906`` reads ``DictIn.residual_value`` (statute-
native per FBTAA s.50). Result: every Residual call landed at the engine as
``$get_dict_ex/3: key 'residual_value' does not exist`` and was surfaced to
the caller as HTTP 502.

The wire mismatch was invisible to the two green gates on either side of it:

1. The engine's own ``test_phase2e_residual.pl`` suite (44/44 pass) constructs
   dicts with the correct ``residual_value`` key at every call site.
2. The pre-existing ``tests/test_wave_a_route_dispatch.py`` gate hermetically
   verified that the router accepts the incoming payload and dispatches to
   engine method=``residual`` / ``in_house_residual`` — but never actually
   inspected the outbound engine payload against the engine's known key set.

This file closes the gap with two orthogonal probes:

* ``test_outbound_engine_payload_carries_residual_value`` — hermetic. Captures
  the outbound engine payload and asserts the key is ``residual_value`` (the
  engine's contract), not ``gst_inclusive_value``. This is the smallest
  possible gate that would have prevented Waqas's 502.
* ``test_residual_openapi_schema_uses_residualValue_alias`` — static. Reads
  the generated OpenAPI spec and asserts ``FBTResidualInput`` +
  ``FBTResidualInHouseInput`` declare property ``residualValue`` (and do
  NOT declare ``gstInclusiveValue``).

The live-PROD smoke probe lives in ``test_production_bundle.py`` next to the
existing Car OC gate (see ``test_residual_live_prod_smoke``).

Lesson honoured: Lesson #40 (hermetic green without production-bundle green
is pre-broken) — this test file plus the extension to ``test_production_bundle.py``
close the calc-api boundary for Residual.
"""
from __future__ import annotations

import json
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

CALC_URIS = [
    "urn:sbrm:calculator:fbt:residual",
    "urn:sbrm:calculator:fbt:residual-in-house",
]
PERIOD_URI = "urn:sbrm:period:fbt:fy2026"


def _mock_residual_engine_response() -> dict:
    """Byte-shape-plausible engine response mirroring
    ``calculate_fbt_residual_internal/3``'s output dict at
    ``FBT_Engine.pl:3903``."""
    return {
        "taxable_value": 500.0,
        "gross_taxable_value": 800.0,
        "reductions": 300.0,
        "in_house_benefit": 0.0,
        "fbt_type": "Type 2",
        "rate_uris_consumed": [],
    }


@pytest.mark.parametrize("calc_uri", CALC_URIS)
def test_outbound_engine_payload_carries_residual_value(
    calc_uri: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The outbound engine payload MUST carry ``residual_value`` (statute-native
    per FBTAA s.50), NOT ``gst_inclusive_value`` (the pre-mc01 copy-paste-from-
    Property defect that surfaced Waqas's 502).
    """
    monkeypatch.delenv("CLAWDOG_RATE_TABLE_ROOT", raising=False)

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calculate_fbt" and request.method == "POST":
            captured["payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json=_mock_residual_engine_response())
        if request.url.path == "/health" and request.method == "GET":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404, json={"error": "unmocked route"})

    transport = httpx.MockTransport(handler)
    mock_client = httpx.AsyncClient(transport=transport)

    from api.main import app
    from api.prolog_client import PrologClient
    from api.routes.calculators import get_prolog_client

    async def _override() -> PrologClient:
        return PrologClient(base_url="http://prolog.test", client=mock_client)

    app.dependency_overrides[get_prolog_client] = _override
    try:
        with TestClient(app) as client:
            url = (
                f"/v1/calculators/{quote(calc_uri, safe='')}/"
                f"{quote(PERIOD_URI, safe='')}"
            )
            body = {
                "residualValue": 800,
                "otherwiseDeductiblePercentage": 0,
                "employeeContribution": 0,
            }
            if "in-house" in calc_uri:
                body["inhouseBenefitClaimed"] = 500
            resp = client.post(url, json=body)
    finally:
        app.dependency_overrides.pop(get_prolog_client, None)

    assert resp.status_code == 200, (
        f"{calc_uri} route did not accept residualValue-shaped body: "
        f"HTTP {resp.status_code} body={resp.text}"
    )
    payload = captured.get("payload")
    assert payload is not None, "engine handler was never called"

    # The primary assertion: the engine payload key is `residual_value`, NOT
    # `gst_inclusive_value`. This is the exact contract at
    # LodgeiT_FBT/FBT_Engine.pl:3906.
    assert "residual_value" in payload, (
        f"outbound engine payload for {calc_uri} is missing `residual_value` "
        f"key. Payload was: {payload!r}. This is the Waqas 2026-07-05 "
        "regression class — the engine's `calculate_fbt_residual_internal/3` "
        "reads `DictIn.residual_value` (FBTAA s.50 statute-native)."
    )
    assert payload["residual_value"] == 800
    assert "gst_inclusive_value" not in payload, (
        f"outbound engine payload for {calc_uri} carries the pre-mc01 "
        f"`gst_inclusive_value` key. Payload was: {payload!r}. This key is "
        "the Property/Housing/etc. convention; the engine's Residual "
        "predicate does NOT read it."
    )
    # Sanity: engine_method + benefit_category dispatch fields still present.
    assert payload["benefit_category"] in ("residual", "residual_in_house")
    assert payload["method"] in ("residual", "in_house_residual")


@pytest.mark.parametrize(
    "schema_name",
    ["FBTResidualInput", "FBTResidualInHouseInput"],
)
def test_residual_openapi_schema_uses_residualValue_alias(schema_name: str) -> None:
    """The generated OpenAPI spec MUST expose ``residualValue`` (statute-native
    per FBTAA s.50) as the primary monetary input on both Residual schemas,
    and MUST NOT expose ``gstInclusiveValue`` (the pre-mc01 defect).
    """
    from api.main import app

    with TestClient(app) as client:
        resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    schema = spec["components"]["schemas"].get(schema_name)
    assert schema is not None, f"OpenAPI missing component: {schema_name}"

    props = schema.get("properties", {})
    assert "residualValue" in props, (
        f"{schema_name} does not declare `residualValue`; properties were "
        f"{sorted(props.keys())!r}. This is a wire-contract regression."
    )
    assert "gstInclusiveValue" not in props, (
        f"{schema_name} still declares `gstInclusiveValue`; this is the "
        f"pre-mc01-2026-07-07 defect. Properties were {sorted(props.keys())!r}."
    )

    # residualValue is required for both variants.
    required = schema.get("required", [])
    assert "residualValue" in required, (
        f"{schema_name} declares `residualValue` but not as required; "
        f"required set was {required!r}."
    )


__all__ = []
