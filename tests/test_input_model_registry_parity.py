"""Per-URN input-model registry parity gate (mut-2026-05-31-mc15).

Binary-failure gate asserting the REST + MCP input-model dispatch dicts
agree. The two dicts:

- ``api.routes.calculators._CALC_INPUT_MODEL_REST`` — used by the generic
  POST /v1/calculators/{calc_uri}/{period_uri} route to validate the
  request body against the per-URN pydantic schema.

- ``api.services.mcp_tool_registry._CALC_INPUT_MODEL`` — used by the
  MCP tools/list surface to resolve the per-URN input JSON Schema.

Both must agree per Lesson #31 (the dispatch table IS the framework; growing
it is the load-bearing application). If they drift, MCP clients see a tool
listed in tools/list whose schema is wrong for the actual REST route OR vice
versa — silent contract drift between the two egresses.

Exception: depreciation lives on a dedicated REST route
``/v1/calculators/depreciation/audit/{period_uri}`` with its own pydantic-typed
body, so it is NOT in ``_CALC_INPUT_MODEL_REST`` (the generic-route dispatch).
It IS in the MCP ``_CALC_INPUT_MODEL`` because tools/list advertises all
calculator URNs uniformly. This single exception is allowlisted below.
"""
from __future__ import annotations

from api.routes.calculators import _CALC_INPUT_MODEL_REST, _CALCULATOR_REGISTRY
from api.services.mcp_tool_registry import _CALC_INPUT_MODEL

# Calculator URNs that live on dedicated REST routes (not the generic
# /v1/calculators/{calc_uri}/{period_uri} dispatch). These appear in the MCP
# input model registry but not in the REST generic-route dispatch.
_DEDICATED_ROUTE_URN_ALLOWLIST = {
    # mc39-2026-08-29 rung 5: depreciation URN migrated from :audit to :at
    # per Fable verdict amendment 2 §A2.8 rider 4.
    "urn:sbrm:calculator:depreciation:at",
    # Phase D (mut-2026-08-24-mc20): Div7A_Engine has its own dedicated
    # REST route /calculators/div7a/at/{period_uri} with native FastAPI
    # response shape; does NOT dispatch through the generic route.
    "urn:sbrm:calculator:div7a:at",
    # NOTE (D53b, Fable [CALC] 2026-09-30): hp:schedule was here, but a
    # generic-route call for it returned HTTP 500 ("missing from
    # _CALC_INPUT_MODEL_REST") on canary 00067-dar. It is now registered in
    # _CALC_INPUT_MODEL_REST with an internal-dispatch branch delegating to
    # invoke_hp_schedule, exactly like depreciation:at / div7a:at, so it is
    # NO LONGER a dedicated-route-only URN.
}


def test_rest_input_models_subset_of_mcp_input_models() -> None:
    """Every REST generic-route URN MUST appear in the MCP input model registry.

    If this fails, the MCP tool's advertised inputSchema diverges from the
    REST route's actual validation schema for the same URN.
    """
    rest_urns = set(_CALC_INPUT_MODEL_REST.keys())
    mcp_urns = set(_CALC_INPUT_MODEL.keys())
    missing_in_mcp = rest_urns - mcp_urns
    assert not missing_in_mcp, (
        f"REST input model registry has URNs not in MCP registry: "
        f"{missing_in_mcp}. Add them to "
        f"api/services/mcp_tool_registry.py::_CALC_INPUT_MODEL."
    )


def test_mcp_input_models_match_rest_for_generic_route_urns() -> None:
    """For every URN in BOTH registries, the input-model class MUST be identical.

    Catches the case where REST + MCP both register an URN but with different
    pydantic classes (silent contract drift between egresses).
    """
    common_urns = set(_CALC_INPUT_MODEL_REST.keys()) & set(_CALC_INPUT_MODEL.keys())
    mismatches = []
    for urn in common_urns:
        rest_model = _CALC_INPUT_MODEL_REST[urn]
        mcp_model = _CALC_INPUT_MODEL[urn]
        if rest_model is not mcp_model:
            mismatches.append(
                f"{urn}: REST={rest_model.__name__} MCP={mcp_model.__name__}"
            )
    assert not mismatches, (
        f"REST + MCP input-model registries disagree on these URNs: "
        f"{mismatches}. Fix by aligning the two dicts."
    )


def test_every_calc_registry_urn_has_a_pydantic_input_model() -> None:
    """Every URN in _CALCULATOR_REGISTRY MUST resolve to a pydantic input class
    via either the REST generic-route dispatch OR the dedicated-route allowlist
    (depreciation today). Otherwise route validation will fall through to 500.
    """
    registry_urns = set(_CALCULATOR_REGISTRY.keys())
    resolvable_urns = set(_CALC_INPUT_MODEL_REST.keys()) | _DEDICATED_ROUTE_URN_ALLOWLIST
    unresolved = registry_urns - resolvable_urns
    assert not unresolved, (
        f"Calculator registry has URNs without a pydantic input model in "
        f"either _CALC_INPUT_MODEL_REST or the dedicated-route allowlist: "
        f"{unresolved}. Add an input model class + register it."
    )


def test_every_registry_urn_resolves_on_the_generic_rest_route() -> None:
    """D53b (Fable [CALC] 2026-09-30): every calculator-registry URN MUST be
    invokable through the generic POST /v1/calculators/{calc_uri}/{period_uri}
    route without a 500. The generic route consults ONLY
    ``_CALC_INPUT_MODEL_REST`` for body validation + dispatch; any registry URN
    absent from it falls through to the HTTP 500
    ``missing from _CALC_INPUT_MODEL_REST`` defect (observed for
    ``urn:sbrm:calculator:hp:schedule`` on canary 00067-dar).

    This is stricter than
    ``test_every_calc_registry_urn_has_a_pydantic_input_model`` above, which
    also accepts the dedicated-route allowlist. Here every URN must resolve in
    the generic-route dispatch table itself. Fails on pre-D53b main (hp missing
    from _CALC_INPUT_MODEL_REST); passes once hp:schedule is registered.
    """
    registry_urns = set(_CALCULATOR_REGISTRY.keys())
    generic_route_urns = set(_CALC_INPUT_MODEL_REST.keys())
    unresolved = registry_urns - generic_route_urns
    assert not unresolved, (
        f"Calculator-registry URNs missing from _CALC_INPUT_MODEL_REST (the "
        f"generic-route dispatch table) — a generic-route call for each will "
        f"return HTTP 500 'missing from _CALC_INPUT_MODEL_REST': {sorted(unresolved)}. "
        f"Register each in api/routes/calculators.py::_CALC_INPUT_MODEL_REST "
        f"(add an internal-dispatch branch for dedicated-route calculators)."
    )


def test_no_orphan_input_models_in_mcp_registry() -> None:
    """Every URN in MCP input model registry MUST be in _CALCULATOR_REGISTRY.

    Catches dead entries in the MCP registry that don't correspond to a real
    calculator (would surface as MCP tools that REST 404 on invocation).
    """
    mcp_urns = set(_CALC_INPUT_MODEL.keys())
    registry_urns = set(_CALCULATOR_REGISTRY.keys())
    orphans = mcp_urns - registry_urns
    assert not orphans, (
        f"MCP input model registry has URNs not in _CALCULATOR_REGISTRY: "
        f"{orphans}. Either add to calculator registry or remove from MCP "
        f"input model registry."
    )
