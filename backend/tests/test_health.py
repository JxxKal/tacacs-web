"""Smoke tests for the health endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_live_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/healthz/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_structured_checks() -> None:
    # The unit-test environment has no live Postgres; the endpoint should
    # still respond with the structured checks payload (and 503 because of
    # the DB check failing).
    with TestClient(app) as client:
        response = client.get("/healthz/ready")
    assert response.status_code in (200, 503)
    body = response.json()
    assert set(body.keys()) == {"status", "checks"}
    assert "db" in body["checks"]
    assert "master_key" in body["checks"]
    # In tests we seed a real master-key file, so that check should pass.
    assert body["checks"]["master_key"] == "ok"
