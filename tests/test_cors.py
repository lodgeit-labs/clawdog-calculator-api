"""CORS middleware binary-failure gate.

Asserts that the FastAPI app responds correctly to a browser-origin
preflight OPTIONS request AND emits ``access-control-allow-origin`` on
the actual response. This is the gate that would have caught the
substrate gap surfaced at ``mut-2026-06-24-mc12``: Waqas's Office.js
Excel add-in fired the first browser-origin consumer of the public API
surface and was blocked by CORS preflight failure (HTTP 405 on every
OPTIONS request, no ACAO header on actual responses); no dogfood probe
to date covered the browser-origin shape.

**Lesson candidate anchor (n=1):** probe-substrate parity \u2014 public-API
substrate gates MUST include a browser-origin-shape probe (OPTIONS
preflight + Origin-bearing GET checking for
``access-control-allow-origin``) before declaring the surface
handover-ready. Server-side dogfood (Python, curl, .NET, ``make
smoke-prod``) is blind to browser-origin failure modes because
Same-Origin Policy is browser-only enforcement.

Cross-references:
  - ``api/main.py`` (CORSMiddleware construction)
  - ``clawdog-brain/memory/2026-06-24-mc12-cors-substrate-fix-sprint-design.md``
  - ``clawdog-brain/memory/lessons.md`` (Lesson candidate slot)
  - ``clawdog-brain/memory/waqas-handover.md`` (substrate-inventory delta)
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


_BROWSER_ORIGIN = "https://localhost:3000"


def _acao_present(response) -> bool:
    """Return True if the response carries ``access-control-allow-origin``."""
    return "access-control-allow-origin" in {k.lower() for k in response.headers}


def test_options_preflight_v1_calculators_returns_200_with_acao() -> None:
    """OPTIONS preflight on ``/v1/calculators`` returns 200 with ACAO header.

    Pre-CORS-middleware state: HTTP 405 ``allow: GET``. Post-middleware:
    HTTP 200 with ``access-control-allow-origin``.
    """
    response = client.options(
        "/v1/calculators",
        headers={
            "Origin": _BROWSER_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200, (
        f"OPTIONS preflight expected 200, got {response.status_code}. "
        "If 405, CORSMiddleware is missing from api/main.py."
    )
    assert _acao_present(response), (
        "OPTIONS preflight response missing ``access-control-allow-origin`` header."
    )


def test_options_preflight_mcp_returns_200_with_acao() -> None:
    """OPTIONS preflight on ``/mcp`` returns 200 with ACAO header."""
    response = client.options(
        "/mcp",
        headers={
            "Origin": _BROWSER_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert _acao_present(response)


def test_options_preflight_openapi_json_returns_200_with_acao() -> None:
    """OPTIONS preflight on ``/openapi.json`` returns 200 with ACAO header."""
    response = client.options(
        "/openapi.json",
        headers={
            "Origin": _BROWSER_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert _acao_present(response)


def test_actual_get_response_v1_calculators_carries_acao() -> None:
    """``GET /v1/calculators`` with Origin returns ACAO in actual response.

    Catches the case where preflight passes but actual response is
    stripped of CORS headers (which would still block browser
    consumers \u2014 the spec requires ACAO on the actual response, not
    just the preflight).
    """
    response = client.get(
        "/v1/calculators",
        headers={"Origin": _BROWSER_ORIGIN},
    )
    assert response.status_code == 200
    assert _acao_present(response), (
        "GET response missing ``access-control-allow-origin`` header even "
        "though Origin was sent. Browser consumers will be blocked."
    )
