"""DB schema smoke test: the simplified Listing table creates cleanly and enforces
the (source, source_id) uniqueness the crawl upsert relies on."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from carcatcher.db import engine as db_engine
from carcatcher.db.models import Listing, ListingStatus


def _engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_creates_and_reads_a_listing():
    engine = _engine()
    with Session(engine) as session:
        session.add(
            Listing(
                source="vw", source_id="1", url="https://x/1", model="id4", trim="Pro",
                price_eur=30000, mileage_km=1000, year=2024, power_kw=150,
                condition="used", location="Berlin", title="VW ID.4 Pro",
            )
        )
        session.commit()
        row = session.exec(
            __import__("sqlmodel").select(Listing).where(Listing.source_id == "1")
        ).one()
        assert row.status == ListingStatus.ACTIVE.value


def test_enforces_source_source_id_uniqueness():
    engine = _engine()
    with Session(engine) as session:
        session.add(Listing(source="vw", source_id="1", url="https://x/1", model="id4", title="A"))
        session.commit()
        session.add(Listing(source="vw", source_id="1", url="https://x/1-dup", model="id4", title="B"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_status_can_be_set_to_gone_and_round_trips():
    engine = _engine()
    with Session(engine) as session:
        session.add(
            Listing(
                source="vw", source_id="1", url="https://x/1", model="id4", title="A",
                status=ListingStatus.GONE.value,
            )
        )
        session.commit()
        row = session.exec(
            __import__("sqlmodel").select(Listing).where(Listing.source_id == "1")
        ).one()
        assert row.status == ListingStatus.GONE.value


def test_removed_legacy_fields_are_not_on_the_model():
    for field in ("battery_kwh", "make", "deal_score", "ai_evaluation", "fair_price_estimate"):
        assert field not in Listing.model_fields


def test_tag_defaults_to_none_and_can_be_set_and_round_trips():
    engine = _engine()
    with Session(engine) as session:
        session.add(
            Listing(source="vw", source_id="1", url="https://x/1", model="id4", title="A")
        )
        session.add(
            Listing(
                source="vw", source_id="2", url="https://x/2", model="id4", title="B",
                tag="star",
            )
        )
        session.commit()
        untagged = session.exec(
            __import__("sqlmodel").select(Listing).where(Listing.source_id == "1")
        ).one()
        tagged = session.exec(
            __import__("sqlmodel").select(Listing).where(Listing.source_id == "2")
        ).one()
        assert untagged.tag is None
        assert tagged.tag == "star"


def test_init_db_adds_tag_column_to_an_existing_table_without_losing_data():
    """Production already has real listing data from before `tag` existed.
    `create_all()` alone only creates missing tables, never missing columns
    on tables that already exist — so `init_db()` must also backfill the
    column onto an already-deployed table without touching existing rows."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    with engine.connect() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE listing (
                id INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                url TEXT NOT NULL,
                model TEXT NOT NULL,
                trim TEXT NOT NULL,
                price_eur INTEGER,
                mileage_km INTEGER,
                year INTEGER,
                power_kw INTEGER,
                condition TEXT NOT NULL,
                location TEXT,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                first_seen_at DATETIME NOT NULL,
                last_seen_at DATETIME NOT NULL
            )
            """
        )
        conn.exec_driver_sql(
            "INSERT INTO listing (id, source, source_id, url, model, trim, condition, title, "
            "status, first_seen_at, last_seen_at) VALUES "
            "(1, 'vw', '1', 'https://x/1', 'id4', '', 'used', 'A', 'active', "
            "'2026-01-01T00:00:00', '2026-01-01T00:00:00')"
        )
        conn.commit()

    db_engine.set_engine(engine)
    try:
        db_engine.init_db()
        with Session(engine) as session:
            row = session.exec(
                __import__("sqlmodel").select(Listing).where(Listing.source_id == "1")
            ).one()
            assert row.tag is None
            assert row.title == "A"  # pre-existing data untouched
    finally:
        db_engine.set_engine(None)  # type: ignore[arg-type]
