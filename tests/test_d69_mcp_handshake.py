"""D69 (Fable [CALC] 2026-11-08): /mcp must accept the standard MCP handshake.

Standard MCP clients send ``initialize`` → ``notifications/initialized`` →
``tools/list`` (then ``tools/call``) before doing anything useful. Before D69
the server rejected ``initialize`` with -32601, so no spec-conformant client
could connect (Argon live evidence 2026-11-07).

These tests drive the real ``/mcp`` route (plain JSON-RPC 2.0 over HTTP POST,
the transport in use) through the mounted app and assert:

  * the full handshake sequence works (initialize → notifications/initialized
    → tools/list → one tools/call on a cheap calculator);
  * the no-initialize path still works (stateless: existing callers rely on it);
  * version negotiation (echo a supported client version; else server latest);
  * ping returns {}; unknown methods stay -32601.

No official MCP client library is installed in the pinned env, so the handshake
is driven as the exact spec JSON-RPC sequence over the real HTTP route rather
than via a client lib (adding an unpinned dependency is not justified here).
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from api import __version__
from api.main import app

_SERVER_LATEST = "2025-06-18"
_CHEAP_TOOL = "fbt-car-operating-cost"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as tc:
        yield tc


def _rpc(client: TestClient, method: str, *, id_=None, params=None):
    body: dict = {"jsonrpc": "2.0", "method": method}
    if id_ is not None:
        body["id"] = id_
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body)


# ---------------------------------------------------------------------------
# Full handshake sequence.
# ---------------------------------------------------------------------------


def test_full_handshake_sequence(client: TestClient) -> None:
    """initialize → notifications/initialized → tools/list → tools/call."""
    # 1. initialize
    init = _rpc(
        client,
        "initialize",
        id_=1,
        params={
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "argon", "version": "1.0"},
        },
    )
    assert init.status_code == 200, init.text
    result = init.json()["result"]
    # Negotiated version: the client asked for a supported version → echoed.
    assert result["protocolVersion"] == "2025-03-26"
    # Capabilities advertise tools + resources.
    assert "tools" in result["capabilities"]
    assert "resources" in result["capabilities"]
    # serverInfo carries name + version.
    assert result["serverInfo"]["name"] == "clawdog-calculator-api"
    assert result["serverInfo"]["version"] == __version__

    # 2. notifications/initialized → HTTP 202, no body.
    notified = _rpc(client, "notifications/initialized")
    assert notified.status_code == 202, notified.text
    assert notified.content == b""

    # 3. tools/list
    listed = _rpc(client, "tools/list", id_=2)
    assert listed.status_code == 200, listed.text
    tools = listed.json()["result"]["tools"]
    assert isinstance(tools, list) and tools
    names = {t["name"] for t in tools}
    assert _CHEAP_TOOL in names

    # 4. one tools/call on a cheap calculator.
    called = _rpc(
        client,
        "tools/call",
        id_=3,
        params={"name": _CHEAP_TOOL, "arguments": {}},
    )
    assert called.status_code == 200, called.text
    call_result = called.json()["result"]
    assert "content" in call_result
    assert call_result["content"][0]["type"] == "text"


# ---------------------------------------------------------------------------
# No-initialize path still works (stateless).
# ---------------------------------------------------------------------------


def test_tools_list_without_initialize(client: TestClient) -> None:
    """Existing callers POST tools/list with no prior initialize — still works."""
    resp = _rpc(client, "tools/list", id_=10)
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json()["result"]["tools"], list)


def test_tools_call_without_initialize(client: TestClient) -> None:
    """tools/call with no prior initialize — still works (stateless)."""
    resp = _rpc(
        client,
        "tools/call",
        id_=11,
        params={"name": _CHEAP_TOOL, "arguments": {}},
    )
    assert resp.status_code == 200, resp.text
    assert "content" in resp.json()["result"]


# ---------------------------------------------------------------------------
# Version negotiation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "requested,expected",
    [
        pytest.param("2025-06-18", "2025-06-18", id="latest-echoed"),
        pytest.param("2025-03-26", "2025-03-26", id="older-supported-echoed"),
        pytest.param("2024-11-05", "2024-11-05", id="oldest-supported-echoed"),
        pytest.param("1999-01-01", _SERVER_LATEST, id="unsupported-falls-to-latest"),
        pytest.param(None, _SERVER_LATEST, id="missing-falls-to-latest"),
    ],
)
def test_initialize_version_negotiation(
    client: TestClient, requested, expected: str
) -> None:
    params: dict = {"capabilities": {}, "clientInfo": {"name": "x", "version": "1"}}
    if requested is not None:
        params["protocolVersion"] = requested
    resp = _rpc(client, "initialize", id_=20, params=params)
    assert resp.status_code == 200, resp.text
    assert resp.json()["result"]["protocolVersion"] == expected


# ---------------------------------------------------------------------------
# ping + unknown-method behaviour.
# ---------------------------------------------------------------------------


def test_ping_returns_empty_object(client: TestClient) -> None:
    resp = _rpc(client, "ping", id_=30)
    assert resp.status_code == 200, resp.text
    assert resp.json()["result"] == {}


def test_unknown_method_still_method_not_found(client: TestClient) -> None:
    resp = _rpc(client, "does/not/exist", id_=31)
    assert resp.status_code == 200, resp.text
    err = resp.json()["error"]
    assert err["code"] == -32601
    # initialize is now in the advertised supported set.
    assert "initialize" in err["data"]["supported"]


def test_initialize_default_capabilities_shape(client: TestClient) -> None:
    """initialize capabilities declare tools + resources with listChanged flags."""
    resp = _rpc(
        client,
        "initialize",
        id_=40,
        params={"protocolVersion": _SERVER_LATEST, "capabilities": {}},
    )
    caps = resp.json()["result"]["capabilities"]
    assert caps["tools"] == {"listChanged": False}
    assert caps["resources"] == {"listChanged": False, "subscribe": False}
