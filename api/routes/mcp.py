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

from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Body, Request, status
from fastapi.responses import JSONResponse, Response

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
_METHOD_TOOLS_LIST = "tools/list"
_METHOD_TOOLS_CALL = "tools/call"
_METHOD_RESOURCES_LIST = "resources/list"
_METHOD_RESOURCES_READ = "resources/read"

_SUPPORTED_METHODS = {
    _METHOD_TOOLS_LIST,
    _METHOD_TOOLS_CALL,
    _METHOD_RESOURCES_LIST,
    _METHOD_RESOURCES_READ,
}


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


@router.post(
    "",
    summary="MCP JSON-RPC endpoint.",
    description=(
        "Single MCP JSON-RPC 2.0 entry point. POST a JSON-RPC envelope; "
        "receive a JSON-RPC result or structured error. Supported methods: "
        "``tools/list``, ``tools/call``, ``resources/list``, ``resources/read``. "
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

    try:
        if method == _METHOD_TOOLS_LIST:
            result: Any = {"tools": mcp_tool_registry.list_tools()}
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
    of ``arguments``, then bridge to the existing REST handler by calling
    the FastAPI app's internal test client mounted at the same process —
    NO out-of-process round trip. The REST handler's existing structured
    error mapping (502/503/422 with JSON detail) is preserved verbatim;
    we wrap it in a JSON-RPC result/error envelope.

    Today: we DO NOT actually invoke the REST handler (the per-route
    bodies have type-checked pydantic models that wouldn't fit a generic
    dispatch path cleanly without route-handler refactor — Lesson #31
    forbids). Instead, ``tools/call`` returns a structured ``redirect``
    payload pointing the MCP client at the equivalent REST URL, so the
    client can either iframe-load the widget OR POST directly to REST.
    This is the n=1 minimal-viable shape; n=2 generalisation (true
    in-process dispatch) is deferred to a future PR when route-handler
    convergence is justified by signal.
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
    # at ``/v1/calculators/depreciation/audit/{period_uri}``.
    base_url = str(request.base_url).rstrip("/")
    if calc_uri == "urn:sbrm:calculator:depreciation:audit":
        rest_path = f"/v1/calculators/depreciation/audit/{quote(period_uri, safe='')}"
    else:
        rest_path = (
            f"/v1/calculators/{quote(calc_uri, safe='')}/"
            f"{quote(period_uri, safe='')}"
        )

    # Strip the period_uri from arguments before surfacing as REST body
    # template (period_uri lives in the URL).
    rest_body_template = {k: v for k, v in arguments.items() if k != "period_uri"}

    # Resolve the widget URL if the client wants to render via iframe
    # rather than direct REST POST. None when no widget mapped.
    from api.services.widget_url_resolver import widget_url_for_calc

    widget_url = widget_url_for_calc(calc_uri)

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"calculator={meta['label']!r} ready to invoke via REST POST "
                    f"{rest_path}. Optional iframe widget: {widget_url or 'none'}."
                ),
            }
        ],
        # MCP Apps-style ``_ui_resource`` extension (omitted when no widget).
        # Clients that don't support MCP Apps see the text content above;
        # clients that do support it iframe-mount widget_url.
        "_dispatch": {
            "kind": "rest_redirect",
            "method": "POST",
            "url": f"{base_url}{rest_path}",
            "body_template": rest_body_template,
            "widget_url": widget_url,
            "calc_uri": calc_uri,
            "period_uri": period_uri,
        },
    }


def _handle_resources_read(params: dict[str, Any]) -> dict[str, Any]:
    """Handle ``resources/read`` — delegate to ``mcp_tool_registry``."""
    uri = params.get("uri")
    if not isinstance(uri, str):
        raise _MCPRequestError(
            _JSONRPC_INVALID_PARAMS, "resources/read params missing 'uri' (string)"
        )
    return mcp_tool_registry.read_resource(uri)


__all__ = ["router"]
