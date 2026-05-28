"""Unit tests for PrologClient.dispatch() and the PrologEngineUnavailable
exception mapping introduced under mc06-2026-05-28 Option-C PR α.

Lessons honoured:
  #40 — these are hermetic tests; the production-bundle gate covers the
         deployed-URL surface separately (Lesson #40 sibling at the Python layer).
  #37 — these tests exercise the dispatcher (the production interface) directly,
         not via the wrapping calculate_fbt() / depreciation_audit() methods.
  #36 — assertions name the exception class and error_code, not paraphrase the
         transport-layer details.

Coverage targets:
  - dispatch() with FBT_ENGINE id + successful response   → returns dict
  - dispatch() with DEPRECIATION_ENGINE id + success      → returns dict
  - dispatch() with unknown engine id                     → ValueError
  - dispatch() on httpx.ConnectError                      → PrologEngineUnavailable(error_code="engine_unreachable")
  - dispatch() on httpx.TimeoutException (ConnectTimeout) → PrologEngineUnavailable(error_code="engine_timeout")
  - dispatch() on httpx.HTTPStatusError (404, 500)        → PrologEngineUnavailable(error_code="engine_http_error")
  - dispatch() on httpx.RemoteProtocolError                → PrologEngineUnavailable(error_code="engine_transport_error")
  - dispatch() on JSON body with {"error": "..."} key     → PrologCalculationError
  - dispatch() result wraps the exception with engine + url metadata
"""
from __future__ import annotations

import httpx
import pytest

from api.prolog_client import (
    DEPRECIATION_ENGINE,
    FBT_ENGINE,
    PrologCalculationError,
    PrologClient,
    PrologEngineUnavailable,
)


def _mock_transport(handler):
    """Build an httpx.AsyncClient using a MockTransport."""
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


@pytest.mark.anyio
async def test_dispatch_fbt_success_returns_dict():
    """dispatch(FBT_ENGINE, payload) returns the parsed JSON dict on success."""
    expected_response = {"taxable_value": 3880.96, "trace": {}}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/calculate_fbt"
        return httpx.Response(200, json=expected_response)

    client = PrologClient(
        base_url="http://fbt-engine.test",
        client=_mock_transport(handler),
    )
    result = await client.dispatch(FBT_ENGINE, {"foo": "bar"})
    assert result == expected_response


@pytest.mark.anyio
async def test_dispatch_depreciation_success_returns_dict():
    """dispatch(DEPRECIATION_ENGINE, payload) returns parsed JSON on success."""
    expected_response = {"status": "ok", "audited_standard_assets": []}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/depreciation/audit"
        return httpx.Response(200, json=expected_response)

    client = PrologClient(
        depreciation_base_url="http://dep-engine.test",
        client=_mock_transport(handler),
    )
    result = await client.dispatch(DEPRECIATION_ENGINE, {"foo": "bar"})
    assert result == expected_response


@pytest.mark.anyio
async def test_dispatch_unknown_engine_raises_value_error():
    """dispatch() with unknown engine id raises ValueError (programmer error)."""
    client = PrologClient(client=_mock_transport(lambda r: httpx.Response(200)))
    with pytest.raises(ValueError, match="unknown engine id"):
        await client.dispatch("nonexistent-engine", {})


@pytest.mark.anyio
async def test_dispatch_connect_error_maps_to_engine_unreachable():
    """httpx.ConnectError → PrologEngineUnavailable(error_code='engine_unreachable')."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = PrologClient(
        depreciation_base_url="http://dep-engine.test",
        client=_mock_transport(handler),
    )
    with pytest.raises(PrologEngineUnavailable) as excinfo:
        await client.dispatch(DEPRECIATION_ENGINE, {})

    exc = excinfo.value
    assert exc.error_code == "engine_unreachable"
    assert exc.engine == DEPRECIATION_ENGINE
    assert "dep-engine.test" in exc.url
    assert "connection refused" in str(exc.detail)


@pytest.mark.anyio
async def test_dispatch_timeout_maps_to_engine_timeout():
    """httpx.TimeoutException → PrologEngineUnavailable(error_code='engine_timeout')."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("connect timeout", request=request)

    client = PrologClient(
        base_url="http://fbt-engine.test",
        client=_mock_transport(handler),
    )
    with pytest.raises(PrologEngineUnavailable) as excinfo:
        await client.dispatch(FBT_ENGINE, {})

    assert excinfo.value.error_code == "engine_timeout"
    assert excinfo.value.engine == FBT_ENGINE


@pytest.mark.anyio
async def test_dispatch_5xx_maps_to_engine_http_error():
    """httpx.HTTPStatusError (5xx) → PrologEngineUnavailable(error_code='engine_http_error')."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    client = PrologClient(
        base_url="http://fbt-engine.test",
        client=_mock_transport(handler),
    )
    with pytest.raises(PrologEngineUnavailable) as excinfo:
        await client.dispatch(FBT_ENGINE, {})

    exc = excinfo.value
    assert exc.error_code == "engine_http_error"
    assert exc.detail["status_code"] == 503
    assert "Service Unavailable" in exc.detail["body"]


@pytest.mark.anyio
async def test_dispatch_4xx_maps_to_engine_http_error():
    """httpx.HTTPStatusError (4xx) → PrologEngineUnavailable(error_code='engine_http_error')."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    client = PrologClient(
        base_url="http://fbt-engine.test",
        client=_mock_transport(handler),
    )
    with pytest.raises(PrologEngineUnavailable) as excinfo:
        await client.dispatch(FBT_ENGINE, {})

    assert excinfo.value.error_code == "engine_http_error"
    assert excinfo.value.detail["status_code"] == 404


@pytest.mark.anyio
async def test_dispatch_remote_protocol_error_maps_to_transport_error():
    """httpx.RemoteProtocolError → PrologEngineUnavailable(error_code='engine_transport_error')."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.RemoteProtocolError("malformed response", request=request)

    client = PrologClient(
        base_url="http://fbt-engine.test",
        client=_mock_transport(handler),
    )
    with pytest.raises(PrologEngineUnavailable) as excinfo:
        await client.dispatch(FBT_ENGINE, {})

    assert excinfo.value.error_code == "engine_transport_error"
    assert "RemoteProtocolError" in str(excinfo.value.detail)


@pytest.mark.anyio
async def test_dispatch_structured_engine_error_maps_to_calculation_error():
    """Response body with {"error": "..."} key → PrologCalculationError (not PrologEngineUnavailable).

    Engine REACHED us successfully; computation failed. Distinct failure class.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "invalid_input", "detail": "negative cost"})

    client = PrologClient(
        base_url="http://fbt-engine.test",
        client=_mock_transport(handler),
    )
    with pytest.raises(PrologCalculationError) as excinfo:
        await client.dispatch(FBT_ENGINE, {})

    assert excinfo.value.error == "invalid_input"
    assert excinfo.value.detail == "negative cost"


@pytest.mark.anyio
async def test_calculate_fbt_wrapper_still_works_via_dispatch():
    """Backward-compat: calculate_fbt() is a thin wrapper around dispatch(FBT_ENGINE)."""
    expected = {"taxable_value": 1234.56}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/calculate_fbt"
        return httpx.Response(200, json=expected)

    client = PrologClient(
        base_url="http://fbt-engine.test",
        client=_mock_transport(handler),
    )
    result = await client.calculate_fbt({"foo": "bar"})
    assert result == expected


@pytest.mark.anyio
async def test_depreciation_audit_wrapper_still_works_via_dispatch():
    """Backward-compat: depreciation_audit() is a thin wrapper around dispatch(DEPRECIATION_ENGINE)."""
    expected = {"status": "ok", "audited_standard_assets": []}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/depreciation/audit"
        return httpx.Response(200, json=expected)

    client = PrologClient(
        depreciation_base_url="http://dep-engine.test",
        client=_mock_transport(handler),
    )
    result = await client.depreciation_audit({"foo": "bar"})
    assert result == expected


@pytest.mark.anyio
async def test_calculate_fbt_wrapper_propagates_engine_unavailable():
    """Backward-compat: calculate_fbt() raises PrologEngineUnavailable on httpx failure
    (PREVIOUSLY raised raw httpx.HTTPStatusError; this is the new shape per mc06)."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = PrologClient(
        base_url="http://fbt-engine.test",
        client=_mock_transport(handler),
    )
    with pytest.raises(PrologEngineUnavailable):
        await client.calculate_fbt({})


@pytest.fixture
def anyio_backend():
    return "asyncio"
