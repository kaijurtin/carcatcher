"""Health endpoint tests."""

from __future__ import annotations

from unittest.mock import patch


def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_503_when_db_down(client):
    with patch("carcatcher.api.routes.health.ping_db", return_value=False):
        resp = client.get("/api/health")
    assert resp.status_code == 503
    assert resp.json()["status"] == "db_unavailable"
