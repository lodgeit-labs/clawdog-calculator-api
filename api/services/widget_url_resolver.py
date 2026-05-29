"""Widget-URL resolver for the calc-api MCP surface.

Maps a calculator URI to the URL of the iframe-loadable widget hosted on the
`clawdog-widget-renderer` static site. The MCP `resources/read` handler
embeds these URLs in `ui_resource` payloads so that MCP clients (Claude
Desktop, OpenClaw webchat, the LodgeiT GL Playground host shell, etc.) can
iframe-mount the widget for input collection instead of presenting raw JSON
schema forms.

**Live deploy URL pattern** (wire-verified 2026-05-29 mc03 04:08 UTC):

    https://lodgeit.org/clawdog-widget-renderer/widgets/<widget-id>/

NOT ``widgets.clawdog.io`` as the original sprint design body draft proposed
(``memory/2026-05-28-option-a-sprint-design.md`` § PR 1). The live deploy
landed on the existing ``lodgeit.org`` Pages host in PR #1 of the
``clawdog-widget-renderer`` repo (sha ``0dfc7551``). Per Lesson #41 (cite the
actual surface, not paper-design phrasing) we point at the live surface; the
DNS migration to ``widgets.clawdog.io`` is a separate operational change that
this resolver follows once it ships.

**Calc-URI ↔ widget-ID mapping discipline** (Lesson #31 honour):

Today's mapping is small (n=2; FBT car operating-cost + depreciation audit)
and explicit. No regex generation, no calc-URI-decomposition magic — a flat
``dict`` keyed by full calc URI. When a third calculator surfaces, this
table grows by one row. Generalisation to calc-URI-decomposition is deferred
until the data shape forces it (Lesson #31 anti-pattern: don't generalise
from one data point).

**Widget existence vs. mapping registration** (Lesson #37 honour):

A registry entry asserts that the calc-URI WOULD route to the named widget
slug; it does NOT assert that the widget is live on the renderer. The MCP
``resources/read`` handler is responsible for surfacing the URL as
`ui_resource`; whether the renderer actually serves a 200 at that URL is a
property of the renderer deploy, NOT of this resolver. The
``test_production_bundle.py`` extension asserts wire-readiness against the
live renderer for the SHIPPED widget slug (``gl-detail-csv-uploader``); FBT
+ depreciation widgets are out-of-scope here and land at Option-A PR 4
(``fbt-car-operating-cost`` widget) and a later sprint for depreciation.
"""
from __future__ import annotations

import os

# Production widget-renderer base URL. Override via env var for staging /
# preview deploys.
DEFAULT_WIDGET_RENDERER_BASE_URL = "https://lodgeit.org/clawdog-widget-renderer"

# Calc-URI to widget-slug mapping.
#
# The widget-slug is the directory name under
# ``clawdog-widget-renderer/widgets/<slug>/`` in the renderer repo. It is
# distinct from the calc-URI; multiple calc-URIs may share one widget
# (e.g. statutory-formula + operating-cost FBT methods sharing one form),
# and one calc-URI may have NO widget yet (the resolver returns ``None``
# in that case and the MCP layer omits the ``ui_resource`` from the
# response).
#
# Phase 4 mut-2026-05-29-mc08 state:
#   - FBT car operating-cost: NO widget shipped today; lands at Option-A PR 4
#   - Depreciation audit:    NO widget shipped today; deferred sprint
#   - GL-detail CSV uploader: SHIPPED at PR #1 of clawdog-widget-renderer,
#     but NOT a calc-URI today; surfaced via a dedicated MCP resource (see
#     ``mcp_tool_registry.STANDALONE_WIDGET_RESOURCES``) rather than as a
#     calc binding.
_CALC_TO_WIDGET_SLUG: dict[str, str] = {
    # Placeholder for the FBT widget that lands at Option-A PR 4. Wired here
    # now so the MCP tool registry can introspect the mapping; the
    # widget-renderer 404 for this slug is EXPECTED today and gates the
    # widget's actual production-bundle assertion to its own PR.
    "urn:sbrm:calculator:fbt:car-operating-cost": "fbt-car-operating-cost",
    # Depreciation audit: no widget mapped today. Deliberate omission so the
    # MCP ``resources/list`` surface only advertises what exists OR has a
    # ratified shipping slot. Adding the row when the widget is authored is a
    # one-line change.
}


def widget_renderer_base_url() -> str:
    """Return the configured widget-renderer base URL.

    Resolution order:
        1. ``CLAWDOG_WIDGET_RENDERER_URL`` env var (override for staging
           deploys or test fixtures).
        2. ``DEFAULT_WIDGET_RENDERER_BASE_URL`` module constant.
    """
    return os.environ.get(
        "CLAWDOG_WIDGET_RENDERER_URL", DEFAULT_WIDGET_RENDERER_BASE_URL
    ).rstrip("/")


def widget_url_for_calc(calc_uri: str) -> str | None:
    """Return the iframe-loadable widget URL for ``calc_uri``, or ``None``.

    Returns ``None`` when:
        - ``calc_uri`` has no mapped widget slug (the typical case during
          early-stage calc onboarding before its widget lands).

    Callers (the MCP ``resources/read`` handler) interpret ``None`` as
    "no widget; client should fall back to JSON-schema-driven form
    rendering or direct ``tools/call`` invocation."
    """
    slug = _CALC_TO_WIDGET_SLUG.get(calc_uri)
    if slug is None:
        return None
    base = widget_renderer_base_url()
    return f"{base}/widgets/{slug}/"


def standalone_widget_url(widget_slug: str) -> str:
    """Return the iframe-loadable URL for a standalone widget by slug.

    Standalone widgets are NOT bound to a single calc-URI (e.g. the
    ``gl-detail-csv-uploader`` is a CSV-upload surface that may feed several
    downstream calculators OR none at all). The MCP ``resources/list``
    handler surfaces these as resources of kind ``standalone_widget``.

    Slug → URL is the same shape as ``widget_url_for_calc``; this is just
    the public entry point that does NOT consult ``_CALC_TO_WIDGET_SLUG``.
    """
    base = widget_renderer_base_url()
    return f"{base}/widgets/{widget_slug}/"


def all_calc_widget_mappings() -> dict[str, str]:
    """Return a defensive copy of the calc-URI → widget-slug mapping.

    Used by the MCP tool registry to advertise which calc-URIs have widget
    bindings (the registry then emits ``ui_resource`` payloads only for
    those entries via ``widget_url_for_calc``).
    """
    return dict(_CALC_TO_WIDGET_SLUG)


__all__ = [
    "DEFAULT_WIDGET_RENDERER_BASE_URL",
    "all_calc_widget_mappings",
    "standalone_widget_url",
    "widget_renderer_base_url",
    "widget_url_for_calc",
]
