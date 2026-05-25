"""Test the /livez public liveness route (mut-2026-05-25-mc11).

The /healthz route is intercepted by Google edge layer for external
traffic on Cloud Run; /livez is the non-reserved public alternative
that routes correctly. Both serve the same body shape.
"""
from __future__ import annotations


def test_livez_returns_ok(fastapi_test_client) -> None:
    """/livez returns 200 with the canonical liveness body."""
    resp = fastapi_test_client.get("/livez")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "clawdog-calculator-api"
    assert "version" in body


def test_livez_matches_healthz_body(fastapi_test_client) -> None:
    """/livez and /healthz return identical body shape (only the path differs)."""
    livez_body = fastapi_test_client.get("/livez").json()
    healthz_body = fastapi_test_client.get("/healthz").json()
    assert livez_body == healthz_body
