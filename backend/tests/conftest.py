"""Shared pytest fixtures: isolated in-memory DB + FastAPI TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from carcatcher.db import engine as db_engine
from carcatcher.main import create_app


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
