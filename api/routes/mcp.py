"""``/mcp`` — Model Context Protocol JSON-RPC surface.

Adds MCP support to the calc-API so MCP-aware clients (Claude Desktop,
OpenClaw webchat, the LodgeiT GL Playground host shell, etc.) can invoke
calculators as MCP **tools** and mount widget UIs as MCP **resources**
without needing knowledge of the underlying REST shape.

**Protocol surface implemented** (subset of MCP spec 2025-06-18):

- ``tools/list``       — enumerate calculator tools
- ``tools/call``       — invoke a calculator (bridges to REST routes)
- ``resources/list``   — enumerate widget resources
- ``resources/read``   — fetch a widget resource (returns ``ui_resource``
                         payload for iframe mounting)

**Transport:** JSON-RPC 2.0 over HTTP POST at ``/mcp``. Single-method
per request (no batching today; deferred until n=2 signal that batching
is needed — Lesson #31). Notification-style requests (no ``id`` field)
return ``204 No Content`` per JSON-RPC convention.

**Lesson #36 honour** — this route handler is thin. All MCP protocol
shape decisions live in ``api.services.mcp_tool_registry``; this module
is the HTTP transport + JSON-RPC envelope.

**Lesson #34 honour** — errors surface as structured JSON-RPC error
objects (``code`` + ``message`` + optional ``data``), NEVER as bare 500
HTML. The same defence-in-depth shape that ``api.routes.calculators``
uses for REST 502/503.

**Authentication:** same posture as the REST surface (currently public
read-only with `allow_origins=["*"]` CORS middleware; auth / IP allow-list
to be added in a future sprint when public-write surfaces land). Per the
mc02-ratified sprint design, MCP-client auth + L402 gating land in later
sprints (CLAWDOG/150).
"""
from __future__ import annotations

import json
from typing import Annotated, Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Body, Request, status
from fastapi.responses import JSONResponse, Response

from api import __version__
from api.routes.calculators import _CALCULATOR_REGISTRY
from api.services import mcp_tool_registry

router = APIRouter(prefix="/mcp", tags=["mcp"])


# JSON-RPC 2.0 error codes (per spec § 5.1).
_JSONRPC_PARSE_ERROR = -32700
_JSONRPC_INVALID_REQUEST = -32600
_JSONRPC_METHOD_NOT_FOUND = -32601
_JSONRPC_INVALID_PARAMS = -32602
_JSONRPC_INTERNAL_ERROR = -32603

# Server-defined MCP-specific error codes (custom range).
_MCP_TOOL_NOT_FOUND = -32001
_MCP_RESOURCE_NOT_FOUND = -32002
_MCP_DISPATCH_FAILED = -32003

# Supported MCP method names.
_METHOD_INITIALIZE = "initialize"
_METHOD_INITIALIZED = "notifications/initialized"
_METHOD_PING = "ping"
_METHOD_TOOLS_LIST = "tools/list"
_METHOD_TOOLS_CALL = "tools/call"
_METHOD_RESOURCES_LIST = "resources/list"
_METHOD_RESOURCES_READ = "resources/read"

_SUPPORTED_METHODS = {
    _METHOD_INITIALIZE,
    _METHOD_INITIALIZED,
    _METHOD_PING,
    _METHOD_TOOLS_LIST,
    _METHOD_TOOLS_CALL,
    _METHOD_RESOURCES_LIST,
    _METHOD_RESOURCES_READ,
}

# MCP lifecycle (spec 2025-06-18 § Lifecycle).
#
# D69 (Fable [CALC] 2026-11-08): standard MCP clients send `initialize`, then
# the `notifications/initialized` notification, before `tools/list`. The server
# previously rejected `initialize` with -32601, so no spec-conformant client
# could connect. These handlers add the lifecycle while keeping the surface
# STATELESS — `tools/list` / `tools/call` still work with no prior `initialize`,
# because existing callers rely on that (plain JSON-RPC POST transport, no
# session state).
#
# `_MCP_PROTOCOL_VERSION` is the server's latest supported spec revision (the
# same revision the rest of this module advertises). Version negotiation echoes
# the client's requested version when the server supports it, else returns this.
_MCP_PROTOCOL_VERSION = "2025-06-18"
_MCP_SUPPORTED_PROTOCOL_VERSIONS = frozenset(
    {"2025-06-18", "2025-03-26", "2024-11-05"}
)
_MCP_SERVER_NAME = "clawdog-calculator-api"


def _jsonrpc_response(
    request_id: Any, result: Any | None = None, error: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 response envelope."""
    envelope: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        envelope["error"] = error
    else:
        envelope["result"] = result
    return envelope


def _jsonrpc_error(
    request_id: Any, code: int, message: str, data: Any | None = None
) -> dict[str, Any]:
    """Build a JSON-RPC error envelope."""
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return _jsonrpc_response(request_id, error=err)


def _negotiate_protocol_version(requested: Any) -> str:
    """Return the protocol version to advertise in the initialize result.

    Spec version negotiation: if the client requests a version the server
    supports, echo it; otherwise return the server's latest supported version
    and let the client decide whether it can proceed.
    """
    if isinstance(requested, str) and requested in _MCP_SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return _MCP_PROTOCOL_VERSION


def _handle_initialize(params: dict[str, Any]) -> dict[str, Any]:
    """Handle ``initialize`` — the MCP lifecycle opener (spec 2025-06-18).

    Returns the negotiated ``protocolVersion``, the server ``capabilities``
    (this server offers ``tools`` and ``resources``; neither emits
    ``listChanged`` notifications on this stateless transport), and
    ``serverInfo`` (name + version). Stateless: no session is created.
    """
    requested = params.get("protocolVersion")
    return {
        "protocolVersion": _negotiate_protocol_version(requested),
        "capabilities": {
            # listChanged=false: stateless transport emits no list-changed
            # notifications. tools/resources are both served.
            "tools": {"listChanged": False},
            "resources": {"listChanged": False, "subscribe": False},
        },
        "serverInfo": {
            "name": _MCP_SERVER_NAME,
            "version": __version__,
        },
    }


@router.post(
    "",
    summary="MCP JSON-RPC endpoint.",
    description=(
        "Single MCP JSON-RPC 2.0 entry point. POST a JSON-RPC envelope; "
        "receive a JSON-RPC result or structured error. Lifecycle methods: "
        "``initialize`` (negotiates protocolVersion, advertises capabilities + "
        "serverInfo), ``notifications/initialized`` (accepted, HTTP 202, no "
        "body), ``ping`` (returns {}). Data methods: ``tools/list``, "
        "``tools/call``, ``resources/list``, ``resources/read``. The surface is "
        "stateless — data methods work with or without a prior ``initialize``. "
        "Per MCP spec 2025-06-18."
    ),
)
async def mcp_endpoint(
    request: Request,
    body: Annotated[dict[str, Any], Body(...)],
) -> Response:
    """Single JSON-RPC dispatch endpoint.

    Routes ``method`` to the corresponding handler in
    ``api.services.mcp_tool_registry``. Returns a JSON-RPC 2.0 envelope
    in every case (success or error). Notification-style requests (no
    ``id`` field per JSON-RPC § 4.1) receive ``204 No Content``.
    """
    # Basic JSON-RPC envelope validation.
    if body.get("jsonrpc") != "2.0":
        return JSONResponse(
            _jsonrpc_error(
                body.get("id"),
                _JSONRPC_INVALID_REQUEST,
                "request envelope missing jsonrpc=2.0",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    method = body.get("method")
    if method is None or not isinstance(method, str):
        return JSONResponse(
            _jsonrpc_error(
                body.get("id"),
                _JSONRPC_INVALID_REQUEST,
                "request envelope missing method (string)",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if method not in _SUPPORTED_METHODS:
        return JSONResponse(
            _jsonrpc_error(
                body.get("id"),
                _JSONRPC_METHOD_NOT_FOUND,
                f"method {method!r} not supported",
                data={"supported": sorted(_SUPPORTED_METHODS)},
            ),
            status_code=status.HTTP_200_OK,  # JSON-RPC errors return 200
        )

    request_id = body.get("id")
    is_notification = "id" not in body
    params: dict[str, Any] = body.get("params") or {}

    # --- MCP lifecycle (D69) ------------------------------------------------
    # notifications/initialized is a notification with NO response body; the
    # spec's Streamable-HTTP transport returns HTTP 202 Accepted for an
    # accepted notification. Handle it before the generic dispatch so it never
    # falls into the 204 notification path or requires an id.
    if method == _METHOD_INITIALIZED:
        return Response(status_code=status.HTTP_202_ACCEPTED)

    try:
        if method == _METHOD_INITIALIZE:
            result: Any = _handle_initialize(params)
        elif method == _METHOD_PING:
            # Spec: ping result is an empty object.
            result = {}
        elif method == _METHOD_TOOLS_LIST:
            result = {"tools": mcp_tool_registry.list_tools()}
        elif method == _METHOD_TOOLS_CALL:
            result = await _handle_tools_call(request, params)
        elif method == _METHOD_RESOURCES_LIST:
            result = {"resources": mcp_tool_registry.list_resources()}
        elif method == _METHOD_RESOURCES_READ:
            result = _handle_resources_read(params)
        else:  # pragma: no cover — covered by _SUPPORTED_METHODS check above
            return JSONResponse(
                _jsonrpc_error(
                    request_id,
                    _JSONRPC_METHOD_NOT_FOUND,
                    f"method {method!r} not supported",
                ),
                status_code=status.HTTP_200_OK,
            )
    except _MCPRequestError as exc:
        return JSONResponse(
            _jsonrpc_error(request_id, exc.code, exc.message, data=exc.data),
            status_code=status.HTTP_200_OK,
        )
    except ValueError as exc:
        # Resource-not-found and tool-name-misspellings surface here from
        # mcp_tool_registry.read_resource() / tool_calc_uri_for_name().
        return JSONResponse(
            _jsonrpc_error(
                request_id, _JSONRPC_INVALID_PARAMS, str(exc)
            ),
            status_code=status.HTTP_200_OK,
        )

    if is_notification:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return JSONResponse(_jsonrpc_response(request_id, result=result))


# --- ``tools/call`` dispatcher -----------------------------------------------


class _MCPRequestError(Exception):
    """Internal error carrying JSON-RPC code + data for the route to surface."""

    def __init__(
        self, code: int, message: str, data: Any | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


async def _handle_tools_call(
    request: Request, params: dict[str, Any]
) -> dict[str, Any]:
    """Handle ``tools/call`` — dispatch to the REST calc routes.

    Per MCP spec, ``params`` carries:
        - ``name``       — tool name (e.g. ``fbt-car-operating-cost``)
        - ``arguments``  — dict of input arguments matching ``inputSchema``

    We map ``name`` back to its calc-URI via
    ``mcp_tool_registry.tool_calc_uri_for_name``, pull ``period_uri`` out
    of ``arguments``, then bridge to the existing REST handler by an
    IN-PROCESS ASGI self-call to the same REST URL — NO out-of-process
    round trip. The REST handler's full stack (per-URN pydantic input
    model + cent checks + engine dispatch + manifest + advisory, and the
    D73 uniform error shapes) runs verbatim; we wrap the response in the
    MCP ``tools/call`` result shape.

    D77 (Fable [CALC] 2026-11-08): this REPLACES the n=1 ``rest_redirect``
    pointer. Previously ``tools/call`` returned only a text pointer
    ("ready to invoke via REST POST ...") and never executed the
    calculator, so MCP clients (Claude custom connector) got no result.
    The n=2 signal arrived, so true in-process dispatch lands here.

    Result shape (MCP spec 2025-06-18 ``tools/call``):
      * REST 200 → ``content: [{type: "text", text: <JSON body>}]`` plus
        ``structuredContent: <same body>``;
      * REST 4xx (400/404/422) → ``isError: true`` with the REST error
        body as the text content (D73 uniform shape preserved);
      * the widget-iframe info stays under ``_dispatch`` so clients that
        render widgets keep working.
    """
    name = params.get("name")
    if not isinstance(name, str):
        raise _MCPRequestError(
            _JSONRPC_INVALID_PARAMS, "tools/call params missing 'name' (string)"
        )

    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise _MCPRequestError(
            _JSONRPC_INVALID_PARAMS, "tools/call params 'arguments' must be object"
        )

    calc_uri = mcp_tool_registry.tool_calc_uri_for_name(name)
    if calc_uri is None:
        raise _MCPRequestError(
            _MCP_TOOL_NOT_FOUND,
            f"tool name {name!r} not found",
            data={
                "available": [
                    tool["name"] for tool in mcp_tool_registry.list_tools()
                ]
            },
        )

    meta = _CALCULATOR_REGISTRY[calc_uri]
    period_uri = arguments.get("period_uri") or (
        meta["supported_periods"][0] if meta.get("supported_periods") else None
    )
    if period_uri is None:
        raise _MCPRequestError(
            _JSONRPC_INVALID_PARAMS,
            f"tools/call arguments missing 'period_uri' (no supported period "
            f"default for calc_uri={calc_uri!r})",
        )

    # Construct the REST URL the client can POST to (or that an MCP client
    # with bridging support can dispatch through). The exact route shape
    # is REST-route-specific; today only FBT car operating-cost lives at
    # ``/v1/calculators/{calc_uri}/{period_uri}`` while depreciation lives
    # at ``/v1/calculators/depreciation/at/{period_uri}`` (mc39-2026-08-29
    # rung 5: audit URN retired, at URN adopted per Fable F1 UPHELD).
    if calc_uri == "urn:sbrm:calculator:depreciation:at":
        rest_path = f"/v1/calculators/depreciation/at/{quote(period_uri, safe='')}"
    else:
        rest_path = (
            f"/v1/calculators/{quote(calc_uri, safe='')}/"
            f"{quote(period_uri, safe='')}"
        )

    # Strip the period_uri from arguments before POSTing as the REST body
    # (period_uri lives in the URL).
    rest_body = {k: v for k, v in arguments.items() if k != "period_uri"}

    # Resolve the widget URL if the client wants to render via iframe in
    # addition to the computed result. None when no widget mapped.
    from api.services.widget_url_resolver import widget_url_for_calc

    widget_url = widget_url_for_calc(calc_uri)

    # In-process ASGI self-call: run the exact REST stack without a network
    # round trip. A fresh inbound request through the same app means the
    # per-URN input model, cent checks, engine dispatch, manifest + advisory,
    # and the D73 uniform error shapes all run verbatim.
    transport = httpx.ASGITransport(app=request.app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://mcp.internal"
    ) as http:
        rest_resp = await http.post(rest_path, json=rest_body)

    try:
        body = rest_resp.json()
    except ValueError:
        body = {"error": "non_json_rest_response", "detail": rest_resp.text[:2000]}

    body_text = json.dumps(body, default=str)
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": body_text}],
    }
    if rest_resp.status_code == 200:
        result["structuredContent"] = body
    else:
        # 400/404/422 (and any other non-200) → MCP tool error. The text
        # content carries the REST error body verbatim (D73 uniform shape).
        result["isError"] = True

    # Preserve the iframe-widget info for clients that render widgets.
    if widget_url:
        result["_dispatch"] = {
            "kind": "widget",
            "widget_url": widget_url,
            "calc_uri": calc_uri,
            "period_uri": period_uri,
        }
    return result


def _handle_resources_read(params: dict[str, Any]) -> dict[str, Any]:
    """Handle ``resources/read`` — delegate to ``mcp_tool_registry``."""
    uri = params.get("uri")
    if not isinstance(uri, str):
        raise _MCPRequestError(
            _JSONRPC_INVALID_PARAMS, "resources/read params missing 'uri' (string)"
        )
    return mcp_tool_registry.read_resource(uri)


__all__ = ["router"]
