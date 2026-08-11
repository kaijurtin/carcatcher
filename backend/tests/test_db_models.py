"""DB schema smoke test: the simplified Listing table creates cleanly and enforces
the (source, source_id) uniqueness the crawl upsert relies on."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

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
