"""Shared pytest fixtures: deterministic settings + isolated DB + TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from carcatcher import config
from carcatcher.config import Settings
from carcatcher.db import engine as db_engine
from carcatcher.main import create_app


@pytest.fixture(autouse=True)
def test_settings():
    """Force deterministic settings: no scheduler, AI off, instant throttle."""
    config._settings = Settings(
        scheduler_enabled=False,
        ai_disabled=True,
        scrape_min_interval_ms=0,
        cron_secret="test-secret",
        prune_gone_days=14,
        run_timeout_minutes=30,
    )
    yield config._settings
    config._settings = None


@pytest.fixture()
def test_engine():
    """A fresh in-memory SQLite engine shared across connections for one test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    db_engine.set_engine(engine)
    yield engine
    db_engine.set_engine(None)  # type: ignore[arg-type]


@pytest.fixture()
def client(test_engine):
    app = create_app()
    with TestClient(app) as c:
        yield c
