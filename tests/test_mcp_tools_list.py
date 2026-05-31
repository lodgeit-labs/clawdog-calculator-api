"""MCP ``tools/list`` protocol shape gate.

Asserts that the calculator registry surfaces correctly through the
``/mcp`` endpoint as MCP tools, with valid JSON Schema input refs and
the calc-URI embedded as a custom ``_calc_uri`` extension.

Phase 4 mut-2026-05-29-mc08 Option-A PR 2.

Lesson honours:
- #40 — production-bundle test exercises the LIVE deploy in
  ``test_production_bundle.py``; this test stays hermetic and asserts
  the MCP protocol shape against the FastAPI app's in-process surface
- #36 — bridge-layer logic asserted independent of route-handler
- #31 — n=2 calculators today (FBT + depreciation); test asserts exactly
  that count, not generalising beyond
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mcp_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Return a TestClient with the app's full router stack mounted."""
    # The autouse `_clawdog_rate_table_root_env` fixture from conftest sets the
    # hermetic rate-table root; the /mcp routes don't consume it but the
    # FastAPI app's other routes do, and `from api.main import app` triggers
    # registry init.
    from api.main import app

    return TestClient(app)


def _jsonrpc_call(
    client: TestClient,
    method: str,
    params: dict[str, Any] | None = None,
    request_id: int = 1,
) -> dict[str, Any]:
    """Helper: POST a JSON-RPC envelope to ``/mcp`` and parse the response."""
    envelope: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
        "id": request_id,
    }
    if params is not None:
        envelope["params"] = params
    resp = client.post("/mcp", json=envelope)
    assert resp.status_code == 200, (
        f"unexpected status {resp.status_code}; body={resp.text}"
    )
    return resp.json()


def test_tools_list_envelope_shape(mcp_client: TestClient) -> None:
    """``tools/list`` returns a valid JSON-RPC 2.0 envelope."""
    body = _jsonrpc_call(mcp_client, "tools/list")
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert "result" in body
    assert "error" not in body


def test_tools_list_surfaces_fourteen_calculators(mcp_client: TestClient) -> None:
    """The 14 calculators registered today surface as 14 MCP tools.

    Per Lesson #31, we assert exactly the count of registered calculators
    rather than ">= 1" or similar generalised assertion. If a fifteenth
    calculator is registered, this assertion fails — the failure is a
    *signal*, not a defect (it requires explicit update of the canonical
    count + acknowledgement that the tools/list surface has grown).

    History:
    - Phase 3a (n=1): fbt-car-operating-cost only.
    - Phase 3c.3.B (n=2): + depreciation-audit.
    - mut-2026-05-31-mc15 Wave A (n=10): + 8 Phase 2a–2e originals.
    - mut-2026-05-31-mc17 Wave B (n=14): + 4 Phase 2f–2i single-method
      (housing + lafha + board + tebe).
    """
    body = _jsonrpc_call(mcp_client, "tools/list")
    tools = body["result"]["tools"]
    assert isinstance(tools, list)
    assert len(tools) == 14, (
        f"expected 14 calculators registered (FBT car-OC + depreciation + "
        f"8 Wave A + 4 Wave B); got {len(tools)}; tools={tools}"
    )

    names = {tool["name"] for tool in tools}
    expected_names = {
        "fbt-car-operating-cost",
        "depreciation-audit",
        # Wave A (mut-2026-05-31-mc15)
        "fbt-loan",
        "fbt-debt-waiver",
        "fbt-expense-payment",
        "fbt-expense-payment-in-house",
        "fbt-property",
        "fbt-property-in-house",
        "fbt-residual",
        "fbt-residual-in-house",
        # Wave B (mut-2026-05-31-mc17)
        "fbt-housing",
        "fbt-lafha",
        "fbt-board",
        "fbt-tebe",
    }
    assert names == expected_names, f"tool name set mismatch: {names ^ expected_names}"


# Backward-compat aliases for any external test discovery referencing prior names.
test_tools_list_surfaces_two_calculators = test_tools_list_surfaces_fourteen_calculators
test_tools_list_surfaces_ten_calculators = test_tools_list_surfaces_fourteen_calculators


def test_tools_list_input_schemas_resolve(mcp_client: TestClient) -> None:
    """Every tool entry carries a resolvable JSON Schema for ``inputSchema``.

    The schema's ``type``, ``properties``, and ``required`` fields are
    structural-completeness markers. We don't assert specific property
    names (those drift with calculator-side schema evolution); we assert
    the JSON Schema shape is well-formed.
    """
    body = _jsonrpc_call(mcp_client, "tools/list")
    tools = body["result"]["tools"]

    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        assert "_calc_uri" in tool, (
            f"tool {tool['name']} missing _calc_uri extension"
        )

        schema = tool["inputSchema"]
        assert schema.get("type") == "object", (
            f"tool {tool['name']} inputSchema.type != 'object'"
        )
        assert "properties" in schema
        # period_uri MUST be advertised so MCP clients know to pass it.
        assert "period_uri" in schema["properties"], (
            f"tool {tool['name']} missing period_uri in inputSchema.properties"
        )
        assert "period_uri" in schema.get("required", []), (
            f"tool {tool['name']} period_uri not in required list"
        )


def test_tools_call_unknown_tool_returns_jsonrpc_error(
    mcp_client: TestClient,
) -> None:
    """``tools/call`` with an unknown tool name returns a structured
    JSON-RPC error with code -32001 (tool not found), NOT a 5xx HTML."""
    body = _jsonrpc_call(
        mcp_client,
        "tools/call",
        params={"name": "not-a-real-tool", "arguments": {}},
    )
    assert "error" in body
    assert body["error"]["code"] == -32001
    assert "available" in body["error"]["data"]


def test_tools_call_missing_period_uri_returns_invalid_params(
    mcp_client: TestClient,
) -> None:
    """``tools/call`` with a registered tool but missing period_uri returns
    the JSON-RPC redirect using the calculator's default period.

    Default period falls back to ``meta["supported_periods"][0]`` so the
    call succeeds; this asserts the default-fallback path.
    """
    body = _jsonrpc_call(
        mcp_client,
        "tools/call",
        params={"name": "fbt-car-operating-cost", "arguments": {}},
    )
    assert "result" in body, f"expected success-with-default; got {body}"
    dispatch = body["result"]["_dispatch"]
    assert dispatch["kind"] == "rest_redirect"
    assert dispatch["calc_uri"] == "urn:sbrm:calculator:fbt:car-operating-cost"
    assert dispatch["period_uri"] == "urn:sbrm:period:fbt:fy2026"


def test_method_not_found_returns_jsonrpc_error(mcp_client: TestClient) -> None:
    """An unsupported method returns JSON-RPC error code -32601."""
    body = _jsonrpc_call(mcp_client, "completions/complete")
    assert body["error"]["code"] == -32601


def test_invalid_jsonrpc_envelope_returns_400(mcp_client: TestClient) -> None:
    """A malformed envelope (missing ``jsonrpc=2.0``) returns HTTP 400 with
    structured JSON-RPC error body."""
    resp = mcp_client.post(
        "/mcp", json={"method": "tools/list", "id": 1}
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == -32600


def test_notification_request_returns_204(mcp_client: TestClient) -> None:
    """A notification-style request (no ``id`` field) returns 204 No Content
    per JSON-RPC § 4.1.
    """
    resp = mcp_client.post(
        "/mcp", json={"jsonrpc": "2.0", "method": "tools/list"}
    )
    assert resp.status_code == 204
