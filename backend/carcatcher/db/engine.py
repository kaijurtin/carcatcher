"""Database engine, session management, and health ping."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from carcatcher.config import get_settings

# Import models so SQLModel.metadata is populated before init_db().
from carcatcher.db import models  # noqa: F401

_engine: Engine | None = None


def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy engine, creating it on first use."""
    global _engine
    if _engine is None:
        settings = get_settings()
        # Ensure the parent directory for the SQLite file exists.
        db_path = Path(settings.database_path)
        if db_path.parent and not db_path.parent.exists():
            os.makedirs(db_path.parent, exist_ok=True)
        _engine = create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
        )
    return _engine


def set_engine(engine: Engine) -> None:
    """Override the engine (used by tests for an in-memory/temp DB)."""
    global _engine
    _engine = engine


def init_db() -> None:
    """Create all tables if they do not yet exist."""
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped session."""
    with Session(get_engine()) as session:
        yield session


def ping_db() -> bool:
    """Return True if the database is reachable (used by /api/health)."""
    try:
        with Session(get_engine()) as session:
            session.exec(text("SELECT 1"))
        return True
    except Exception:
        return False
