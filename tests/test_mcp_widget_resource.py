"""MCP ``resources/list`` + ``resources/read`` widget-URL gate.

Asserts that:
1. ``resources/list`` enumerates standalone widgets + calc-bound widgets.
2. ``resources/read`` returns a valid ``_ui_resource`` block with a
   widget URL that points at the production widget-renderer host.
3. The widget URL shape matches the live deploy (``lodgeit.org/
   clawdog-widget-renderer/widgets/<slug>/`` per wire-verification
   mc03-2026-05-29).

Phase 4 mut-2026-05-29-mc08 Option-A PR 2.

Lesson honours:
- #41 — assert against the LIVE-DEPLOYED widget URL shape, not paper-design
  ``widgets.clawdog.io`` phrasing
- #37 — distinguish wind-tunnel (GL Detail CSV uploader, shipped) from
  production surface (FBT widget, not yet shipped); both are advertised
  through this surface but only the CSV uploader is wire-resolvable today
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mcp_client() -> TestClient:
    from api.main import app

    return TestClient(app)


def _jsonrpc_call(
    client: TestClient, method: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    envelope: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "id": 1}
    if params is not None:
        envelope["params"] = params
    resp = client.post("/mcp", json=envelope)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_resources_list_includes_standalone_csv_uploader(
    mcp_client: TestClient,
) -> None:
    """The shipped GL Detail CSV uploader widget is advertised as a
    standalone resource (NOT calc-bound)."""
    body = _jsonrpc_call(mcp_client, "resources/list")
    resources = body["result"]["resources"]
    csv_uris = [
        r for r in resources
        if r["uri"] == "urn:clawdog:widget:standalone:gl-detail-csv-uploader"
    ]
    assert len(csv_uris) == 1, (
        f"expected exactly one CSV uploader resource; got {csv_uris}"
    )
    assert csv_uris[0]["mimeType"] == "text/html"


def test_resources_list_includes_calc_bound_widgets(mcp_client: TestClient) -> None:
    """Every calc-URI with a widget mapping surfaces as a calc-bound resource.

    Today: FBT car operating-cost. When OT #82 (FBT widget) lands at
    Option-A PR 4, the widget URL becomes resolvable on the renderer; the
    mapping is wired in advance so the MCP surface is ready (Lesson #37
    architectural distinction).
    """
    body = _jsonrpc_call(mcp_client, "resources/list")
    resources = body["result"]["resources"]
    fbt_calc_resources = [
        r for r in resources
        if r["uri"]
        == "urn:clawdog:widget:calc:urn:sbrm:calculator:fbt:car-operating-cost"
    ]
    assert len(fbt_calc_resources) == 1, fbt_calc_resources


def test_resources_read_csv_uploader_returns_live_renderer_url(
    mcp_client: TestClient,
) -> None:
    """``resources/read`` for the CSV uploader returns the live
    ``lodgeit.org/clawdog-widget-renderer`` URL (Lesson #41 — actual surface
    not paper-design phrasing).
    """
    body = _jsonrpc_call(
        mcp_client,
        "resources/read",
        params={
            "uri": "urn:clawdog:widget:standalone:gl-detail-csv-uploader",
        },
    )
    contents = body["result"]["contents"]
    assert len(contents) == 1
    ui_resource = contents[0]["_ui_resource"]
    assert ui_resource["kind"] == "standalone_widget"
    assert ui_resource["calc_uri"] is None
    assert ui_resource["widget_url"] == (
        "https://lodgeit.org/clawdog-widget-renderer/"
        "widgets/gl-detail-csv-uploader/"
    )


def test_resources_read_calc_bound_returns_widget_url(
    mcp_client: TestClient,
) -> None:
    """Calc-bound resource read returns the mapped widget URL + calc_uri
    in the ``_ui_resource`` block."""
    body = _jsonrpc_call(
        mcp_client,
        "resources/read",
        params={
            "uri": (
                "urn:clawdog:widget:calc:"
                "urn:sbrm:calculator:fbt:car-operating-cost"
            ),
        },
    )
    contents = body["result"]["contents"]
    ui_resource = contents[0]["_ui_resource"]
    assert ui_resource["kind"] == "calc_widget"
    assert ui_resource["calc_uri"] == "urn:sbrm:calculator:fbt:car-operating-cost"
    assert ui_resource["widget_url"].endswith(
        "/widgets/fbt-car-operating-cost/"
    )


def test_resources_read_unknown_uri_returns_invalid_params(
    mcp_client: TestClient,
) -> None:
    """Reading an unknown resource URI returns JSON-RPC error -32602."""
    body = _jsonrpc_call(
        mcp_client,
        "resources/read",
        params={"uri": "urn:clawdog:widget:standalone:does-not-exist"},
    )
    assert "error" in body
    assert body["error"]["code"] == -32602


def test_resources_read_unknown_prefix_returns_invalid_params(
    mcp_client: TestClient,
) -> None:
    """A URI that doesn't match either known prefix is rejected."""
    body = _jsonrpc_call(
        mcp_client,
        "resources/read",
        params={"uri": "https://not.a.urn.example/"},
    )
    assert "error" in body
    assert body["error"]["code"] == -32602


def test_widget_url_resolver_respects_env_override(
    monkeypatch: pytest.MonkeyPatch, mcp_client: TestClient
) -> None:
    """``CLAWDOG_WIDGET_RENDERER_URL`` env var overrides the default base.

    Critical for staging deploys + test fixtures pointing at preview
    renderer URLs.
    """
    monkeypatch.setenv(
        "CLAWDOG_WIDGET_RENDERER_URL", "https://staging.example/wr"
    )

    body = _jsonrpc_call(
        mcp_client,
        "resources/read",
        params={
            "uri": "urn:clawdog:widget:standalone:gl-detail-csv-uploader",
        },
    )
    ui_resource = body["result"]["contents"][0]["_ui_resource"]
    assert ui_resource["widget_url"] == (
        "https://staging.example/wr/widgets/gl-detail-csv-uploader/"
    )
