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


# Columns added to existing tables after their first creation. `create_all` only
# creates missing *tables*, never missing *columns*, and this project has no Alembic —
# so newly added model columns must be backfilled onto already-deployed SQLite DBs.
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "listing": {
        "battery_kwh": "FLOAT",
        "battery_soh_pct": "INTEGER",
        "model_locked": "BOOLEAN NOT NULL DEFAULT 0",
    },
}


def _ensure_added_columns(engine: Engine) -> None:
    """Idempotently add any model columns missing from an existing table (SQLite)."""
    with engine.connect() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            existing = {
                row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            if not existing:
                continue  # table absent — create_all will have made it fresh with all cols
            for name, sqltype in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {name} {sqltype}"
                    )
        conn.commit()


def init_db() -> None:
    """Create all tables if they do not yet exist, then backfill any added columns."""
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    _ensure_added_columns(engine)


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
