"""Refresh + runs endpoint tests."""

from __future__ import annotations

import carcatcher.api.routes.refresh as refresh_mod
from sqlmodel import Session

from carcatcher.db.engine import get_engine
from carcatcher.db.models import CrawlRun, RunStatus


def test_refresh_requires_secret(client):
    assert client.post("/api/refresh").status_code == 401
    assert client.post(
        "/api/refresh", headers={"X-Cron-Secret": "wrong"}
    ).status_code == 401


def test_refresh_409_when_running(client):
    with Session(get_engine()) as s:
        s.add(CrawlRun(source="kleinanzeigen", status=RunStatus.RUNNING.value))
        s.commit()
    resp = client.post("/api/refresh", headers={"X-Cron-Secret": "test-secret"})
    assert resp.status_code == 409


def test_refresh_202_schedules(client, monkeypatch):
    called = {}

    async def fake_run_all(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr(refresh_mod, "run_all_sources", fake_run_all)
    resp = client.post("/api/refresh", headers={"X-Cron-Secret": "test-secret"})
    assert resp.status_code == 202
    assert resp.json()["status"] == "scheduled"


def test_runs_lists_recent(client):
    with Session(get_engine()) as s:
        s.add(CrawlRun(source="kleinanzeigen", status=RunStatus.DONE.value,
                       listings_new=5, est_cost_usd=0.01))
        s.commit()
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["listings_new"] == 5
    assert body[0]["status"] == "done"
