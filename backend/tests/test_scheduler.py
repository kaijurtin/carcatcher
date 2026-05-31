"""Scheduler wiring tests (no scheduler is actually started)."""

from __future__ import annotations

import carcatcher.scheduler.jobs as jobs


def test_build_scheduler_registers_crawl_job(test_settings):
    scheduler = jobs.build_scheduler()
    try:
        job = scheduler.get_job("crawl_kleinanzeigen")
        assert job is not None
        assert job.max_instances == 1
    finally:
        scheduler.shutdown(wait=False) if scheduler.running else None


async def test_scheduled_crawl_invokes_all_sources(monkeypatch):
    called = {}

    async def fake_run_all(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr(jobs, "run_all_sources", fake_run_all)
    await jobs.scheduled_crawl()
    assert called == {"trigger": "scheduled"}


async def test_scheduled_crawl_swallows_errors(monkeypatch):
    async def boom(**kwargs):
        raise RuntimeError("pipeline down")

    monkeypatch.setattr(jobs, "run_all_sources", boom)
    # Should not raise — errors are logged inside scheduled_crawl.
    await jobs.scheduled_crawl()
