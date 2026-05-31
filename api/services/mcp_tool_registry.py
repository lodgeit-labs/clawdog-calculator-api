"""MCP tool registry — maps the calculator constellation to MCP tool definitions.

Sources its data from the existing ``_CALCULATOR_REGISTRY`` in
``api.routes.calculators`` (the single source of truth for which calculators
are wired into the REST surface) and from the JSON Schema definitions exposed
by ``api.schemas.*``. NO calculator-specific logic lives here — the registry
iterates whatever the REST surface already lists, so adding a third
calculator to ``_CALCULATOR_REGISTRY`` automatically surfaces it as a third
MCP tool without code changes here.

This is the bridge between the existing REST contract and the MCP
JSON-RPC contract added in Phase 4 (`mut-2026-05-29-mc08` Option-A PR 2).

**MCP protocol surface advertised** (subset of MCP spec 2025-06-18):

- ``tools/list``  → one entry per row in ``_CALCULATOR_REGISTRY``; each
  entry's ``inputSchema`` is the resolved pydantic JSON Schema
- ``tools/call``  → bridges to the calc-API's REST ``POST
  /v1/calculators/{calc_uri}/{period_uri}`` route (or the depreciation
  sibling route) by reading the calculator URI from ``arguments.calc_uri``
  and forwarding the rest of ``arguments`` as the request body
- ``resources/list`` → emits one ``standalone_widget`` resource per shipped
  standalone widget (today: ``gl-detail-csv-uploader``) plus one
  ``calc_widget`` resource per calc-URI that has a widget mapping
- ``resources/read`` → returns an ``ui_resource`` block with
  ``widget_url`` for iframe mounting; structured ``{error}`` if the
  resource URI is unrecognised

**Lesson #36 honour** — this module is the "bridge" layer; route handlers
in ``api.routes.mcp`` stay thin and delegate to functions here. All MCP
protocol shape decisions (tool definition shape, resource URI scheme,
``ui_resource`` payload format) live here, not in the route handler.

**Lesson #31 honour** — we ship the registry for the n=2 calculators
that currently exist (FBT car operating-cost + depreciation audit). NO
abstraction layer for prompt templates, sampling preferences, or
multi-calculator transactional batches; those wait for n≥2 signal that
they're needed.
"""
from __future__ import annotations

from typing import Any

from api.routes.calculators import _CALCULATOR_REGISTRY
from api.schemas.depreciation import DepreciationAuditInput
from api.schemas.invocation import (
    FBTBoardInput,
    FBTCarOperatingCostInput,
    FBTCarParkingActualInput,
    FBTCarParkingRegister12WkInput,
    FBTCarParkingStatutory228Input,
    FBTCarStatutoryFormulaInput,
    FBTDebtWaiverInput,
    FBTExpensePaymentInHouseInput,
    FBTExpensePaymentInput,
    FBTHousingInput,
    FBTLafhaInput,
    FBTLoanInput,
    FBTMealEntertainment5050Input,
    FBTMealEntertainmentRegister12WkInput,
    FBTPropertyInHouseInput,
    FBTPropertyInput,
    FBTResidualInHouseInput,
    FBTResidualInput,
    FBTTebeInput,
)
from api.services.widget_url_resolver import (
    all_calc_widget_mappings,
    standalone_widget_url,
    widget_url_for_calc,
)

# Map of calc-URI → pydantic model carrying the input JSON Schema.
#
# Hand-maintained because the existing ``_CALCULATOR_REGISTRY`` stores a
# JSON Schema *reference* (``input_schema_ref``) rather than the model
# class itself. Per Lesson #31, adding a third calculator means adding one
# row here AND one row in ``_CALCULATOR_REGISTRY`` — explicit + boring,
# NOT magic.
_CALC_INPUT_MODEL: dict[str, type[Any]] = {
    "urn:sbrm:calculator:fbt:car-operating-cost": FBTCarOperatingCostInput,
    # --- Wave A Phase 2a–2e public-API widening (mut-2026-05-31-mc15) -----
    # Mirrors api.routes.calculators._CALC_INPUT_MODEL_REST; both must agree
    # per tests/test_input_model_registry_parity.py binary-failure gate.
    "urn:sbrm:calculator:fbt:loan": FBTLoanInput,
    "urn:sbrm:calculator:fbt:debt-waiver": FBTDebtWaiverInput,
    "urn:sbrm:calculator:fbt:expense-payment": FBTExpensePaymentInput,
    "urn:sbrm:calculator:fbt:expense-payment-in-house": FBTExpensePaymentInHouseInput,
    "urn:sbrm:calculator:fbt:property": FBTPropertyInput,
    "urn:sbrm:calculator:fbt:property-in-house": FBTPropertyInHouseInput,
    "urn:sbrm:calculator:fbt:residual": FBTResidualInput,
    "urn:sbrm:calculator:fbt:residual-in-house": FBTResidualInHouseInput,
    # --- Wave B Phase 2f–2i public-API widening (mut-2026-05-31-mc17) -----
    "urn:sbrm:calculator:fbt:housing": FBTHousingInput,
    "urn:sbrm:calculator:fbt:lafha": FBTLafhaInput,
    "urn:sbrm:calculator:fbt:board": FBTBoardInput,
    "urn:sbrm:calculator:fbt:tebe": FBTTebeInput,
    # --- Wave C Phase 2j–2k + Car-SF public-API widening (mut-2026-05-31-mc19) -----
    "urn:sbrm:calculator:fbt:car-parking-actual": FBTCarParkingActualInput,
    "urn:sbrm:calculator:fbt:car-parking-statutory-228": FBTCarParkingStatutory228Input,
    "urn:sbrm:calculator:fbt:car-parking-register-12wk": FBTCarParkingRegister12WkInput,
    "urn:sbrm:calculator:fbt:meal-entertainment-50-50": FBTMealEntertainment5050Input,
    "urn:sbrm:calculator:fbt:meal-entertainment-register-12wk": FBTMealEntertainmentRegister12WkInput,
    "urn:sbrm:calculator:fbt:car-statutory-formula": FBTCarStatutoryFormulaInput,
    "urn:sbrm:calculator:depreciation:audit": DepreciationAuditInput,
}


# Standalone widgets advertised through ``resources/list``. These are
# widgets NOT bound to a single calc-URI; today only the GL Detail CSV
# uploader exists. The mapping is widget-slug → human label / description.
STANDALONE_WIDGET_RESOURCES: dict[str, dict[str, str]] = {
    "gl-detail-csv-uploader": {
        "title": "GL Detail CSV Uploader",
        "description": (
            "Upload a General Ledger Detail CSV to the ClawDog calculator-API "
            "for ingestion + classification. Shipped at PR #1 of "
            "lodgeit-labs/clawdog-widget-renderer (sha 0dfc7551)."
        ),
    },
}


# Resource URI scheme — used as the canonical identifier the MCP client
# sends in ``resources/read``. Two schemes:
#
#   urn:clawdog:widget:calc:<calc_uri>    → calc-bound widget (resolves via
#                                            widget_url_for_calc)
#   urn:clawdog:widget:standalone:<slug>  → standalone widget (resolves via
#                                            standalone_widget_url)
_RESOURCE_URI_CALC_PREFIX = "urn:clawdog:widget:calc:"
_RESOURCE_URI_STANDALONE_PREFIX = "urn:clawdog:widget:standalone:"


def list_tools() -> list[dict[str, Any]]:
    """Return the MCP ``tools/list`` payload — one entry per calculator.

    Each entry conforms to the MCP ``Tool`` shape (spec 2025-06-18):
        - ``name``         — short identifier; we use the calculator URI's
                             last two URN segments joined with a hyphen
        - ``description``  — the registry's ``label`` field
        - ``inputSchema``  — JSON Schema (from the pydantic model)

    The ``calc_uri`` is embedded in ``inputSchema.properties`` as a
    ``const`` field so the MCP client passes it back in ``tools/call``
    without ambiguity.
    """
    out: list[dict[str, Any]] = []
    for calc_uri, meta in _CALCULATOR_REGISTRY.items():
        model = _CALC_INPUT_MODEL.get(calc_uri)
        if model is None:
            # A calc-URI in _CALCULATOR_REGISTRY without an _CALC_INPUT_MODEL
            # row is a registry-sync drift — surface explicitly so it shows
            # up in tests/CI rather than silently disappearing from the MCP
            # tools list (Lesson #34: surface, do not paper over).
            input_schema: dict[str, Any] = {
                "type": "object",
                "title": meta["label"],
                "description": (
                    f"NOTE: calc_uri={calc_uri!r} is registered in the REST "
                    f"surface but has no pydantic input model wired into "
                    f"api.services.mcp_tool_registry._CALC_INPUT_MODEL. "
                    f"Tools/call invocations will fail."
                ),
                "properties": {},
            }
        else:
            input_schema = model.model_json_schema()

        # Embed the period_uri as a required argument so the MCP client
        # passes it back. We pick the first supported period as the default;
        # callers can override.
        supported_periods = meta.get("supported_periods", [])
        if supported_periods:
            input_schema.setdefault("properties", {})
            input_schema["properties"]["period_uri"] = {
                "type": "string",
                "description": (
                    "URN-encoded period identifier. "
                    f"Supported: {supported_periods}."
                ),
                "enum": list(supported_periods),
                "default": supported_periods[0],
            }
            required = set(input_schema.get("required", []))
            required.add("period_uri")
            input_schema["required"] = sorted(required)

        out.append(
            {
                "name": _tool_name_for(calc_uri),
                "description": meta["label"],
                "inputSchema": input_schema,
                # Custom extension field — Calc URI for the calling route
                # to dispatch on. Per MCP spec, additional fields outside
                # the protocol's defined shape are permitted.
                "_calc_uri": calc_uri,
                "_jurisdiction": meta.get("jurisdiction"),
            }
        )
    return out


def _tool_name_for(calc_uri: str) -> str:
    """Derive the MCP tool ``name`` from a calc URI.

    Pattern: take the URN's last two segments joined with hyphen. So
    ``urn:sbrm:calculator:fbt:car-operating-cost`` → ``fbt-car-operating-cost``
    and ``urn:sbrm:calculator:depreciation:audit`` → ``depreciation-audit``.
    """
    parts = calc_uri.split(":")
    if len(parts) < 2:
        return calc_uri  # pragma: no cover — defensive
    return f"{parts[-2]}-{parts[-1]}"


def list_resources() -> list[dict[str, Any]]:
    """Return the MCP ``resources/list`` payload.

    Emits one entry per standalone widget + one entry per calc-URI with a
    widget mapping. Each entry carries:
        - ``uri``          — canonical resource URI (see scheme above)
        - ``name``         — short identifier for client display
        - ``description``  — human prose
        - ``mimeType``     — always ``text/html`` for iframe-loadable widgets
    """
    out: list[dict[str, Any]] = []

    # Standalone widgets first (the only one shipped today is the CSV uploader).
    for slug, meta in STANDALONE_WIDGET_RESOURCES.items():
        out.append(
            {
                "uri": f"{_RESOURCE_URI_STANDALONE_PREFIX}{slug}",
                "name": slug,
                "title": meta["title"],
                "description": meta["description"],
                "mimeType": "text/html",
            }
        )

    # Calc-bound widgets (mappings registered today; the actual widget may
    # not yet be live on the renderer — that's intentional per Lesson #37).
    for calc_uri, slug in all_calc_widget_mappings().items():
        meta = _CALCULATOR_REGISTRY.get(calc_uri, {})
        out.append(
            {
                "uri": f"{_RESOURCE_URI_CALC_PREFIX}{calc_uri}",
                "name": slug,
                "title": meta.get("label", slug),
                "description": (
                    f"Iframe-loadable widget for calc_uri={calc_uri}. "
                    f"Widget slug: {slug}."
                ),
                "mimeType": "text/html",
            }
        )

    return out


def read_resource(uri: str) -> dict[str, Any]:
    """Return the MCP ``resources/read`` payload for ``uri``.

    Shape:
        {
            "contents": [
                {
                    "uri": <input uri>,
                    "mimeType": "text/html",
                    "_ui_resource": {
                        "widget_url": "https://...",
                        "kind": "calc_widget" | "standalone_widget",
                        "calc_uri": <calc_uri | null>,
                    },
                }
            ]
        }

    Raises ``ValueError`` if ``uri`` is not a recognised resource URI.

    The ``_ui_resource`` field is a custom extension matching the MCP
    Apps proposed-spec shape (UI resources delivered alongside text
    contents); the route layer surfaces this verbatim so MCP clients
    that support MCP Apps can iframe-mount the widget while clients that
    don't support MCP Apps see the underlying text contents (empty here)
    without breaking.
    """
    if uri.startswith(_RESOURCE_URI_CALC_PREFIX):
        calc_uri = uri[len(_RESOURCE_URI_CALC_PREFIX) :]
        widget_url = widget_url_for_calc(calc_uri)
        if widget_url is None:
            raise ValueError(
                f"resource uri={uri!r} references calc_uri={calc_uri!r} which "
                f"has no widget mapping in api.services.widget_url_resolver."
            )
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "text/html",
                    "_ui_resource": {
                        "widget_url": widget_url,
                        "kind": "calc_widget",
                        "calc_uri": calc_uri,
                    },
                }
            ]
        }

    if uri.startswith(_RESOURCE_URI_STANDALONE_PREFIX):
        slug = uri[len(_RESOURCE_URI_STANDALONE_PREFIX) :]
        if slug not in STANDALONE_WIDGET_RESOURCES:
            raise ValueError(
                f"resource uri={uri!r} references standalone widget "
                f"slug={slug!r} which is not in "
                f"api.services.mcp_tool_registry.STANDALONE_WIDGET_RESOURCES."
            )
        widget_url = standalone_widget_url(slug)
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "text/html",
                    "_ui_resource": {
                        "widget_url": widget_url,
                        "kind": "standalone_widget",
                        "calc_uri": None,
                    },
                }
            ]
        }

    raise ValueError(
        f"resource uri={uri!r} does not match any known prefix "
        f"({_RESOURCE_URI_CALC_PREFIX!r} or {_RESOURCE_URI_STANDALONE_PREFIX!r})."
    )


def tool_calc_uri_for_name(name: str) -> str | None:
    """Reverse-lookup: MCP tool ``name`` → calc URI.

    Used by the ``tools/call`` handler to map the client-supplied tool name
    back to the registry entry it should dispatch to.
    """
    for calc_uri in _CALCULATOR_REGISTRY:
        if _tool_name_for(calc_uri) == name:
            return calc_uri
    return None


__all__ = [
    "STANDALONE_WIDGET_RESOURCES",
    "list_resources",
    "list_tools",
    "read_resource",
    "tool_calc_uri_for_name",
]
