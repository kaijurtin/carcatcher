"""Idempotent column backfill for DBs created before a column was added."""

from __future__ import annotations

from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from carcatcher.db.engine import _ensure_added_columns


def _table_columns(engine, table: str) -> set[str]:
    with engine.connect() as conn:
        return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}


def test_backfills_missing_battery_columns_on_legacy_table():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    # Simulate a legacy schema: listing table without the battery columns.
    with engine.connect() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE listing (id INTEGER PRIMARY KEY, make TEXT, model TEXT)"
        )
        conn.commit()
    assert "battery_kwh" not in _table_columns(engine, "listing")

    _ensure_added_columns(engine)

    cols = _table_columns(engine, "listing")
    assert {"battery_kwh", "battery_soh_pct"} <= cols


def test_backfill_is_idempotent():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    with engine.connect() as conn:
        conn.exec_driver_sql("CREATE TABLE listing (id INTEGER PRIMARY KEY, make TEXT)")
        conn.commit()
    _ensure_added_columns(engine)
    _ensure_added_columns(engine)  # second run must not raise (columns already exist)
    assert {"battery_kwh", "battery_soh_pct"} <= _table_columns(engine, "listing")


def test_no_op_when_table_absent():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    _ensure_added_columns(engine)  # no listing table -> must not raise
