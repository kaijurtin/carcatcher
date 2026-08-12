"""Tests for crawl orchestration: upsert + gone-marking + partial-failure handling."""

from __future__ import annotations

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from carcatcher.crawl import run_crawl
from carcatcher.db.models import Listing, ListingStatus
from carcatcher.scraping.base import RawListing


def _engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


class FakeParser:
    def __init__(self, name, by_model):
        self.name = name
        self._by_model = by_model

    def fetch_listings(self, model):
        return self._by_model.get(model, [])


class FailingParser:
    name = "broken"

    def fetch_listings(self, model):
        raise RuntimeError("boom")


def _raw(source, source_id, model="id4", price=30000, location="Berlin"):
    return RawListing(
        source=source, source_id=source_id, url=f"https://x/{source_id}",
        model=model, trim="Pro", price_eur=price, mileage_km=1000, year=2024,
        power_kw=150, battery_kwh=None, condition="used", location=location, title="VW ID.4 Pro",
    )


def test_first_crawl_inserts_new_listings():
    engine = _engine()
    parsers = {"vw": FakeParser("vw", {"id4": [_raw("vw", "1")], "id3": []})}
    with Session(engine) as session:
        summary = run_crawl(session, parsers)
        assert summary.added == 1
        assert summary.updated == 0
        rows = session.exec(select(Listing)).all()
        assert len(rows) == 1
        assert rows[0].status == ListingStatus.ACTIVE.value


def test_second_crawl_updates_existing_and_marks_missing_gone():
    engine = _engine()
    with Session(engine) as session:
        run_crawl(
            session,
            {"vw": FakeParser("vw", {"id4": [_raw("vw", "1"), _raw("vw", "2")], "id3": []})},
        )

    with Session(engine) as session:
        # listing "2" disappears, listing "1" reappears with a new price
        summary = run_crawl(
            session,
            {"vw": FakeParser("vw", {"id4": [_raw("vw", "1", price=29000)], "id3": []})},
        )
        assert summary.updated == 1
        assert summary.gone == 1
        rows = {r.source_id: r for r in session.exec(select(Listing)).all()}
        assert rows["1"].status == ListingStatus.ACTIVE.value
        assert rows["1"].price_eur == 29000
        assert rows["2"].status == ListingStatus.GONE.value


def test_failed_source_does_not_mark_its_listings_gone():
    engine = _engine()
    with Session(engine) as session:
        run_crawl(session, {"vw": FakeParser("vw", {"id4": [_raw("vw", "1")], "id3": []})})

    with Session(engine) as session:
        summary = run_crawl(session, {"vw": FailingParser()})
        assert summary.failed_sources == ["vw"]
        assert summary.gone == 0
        row = session.exec(select(Listing).where(Listing.source_id == "1")).one()
        assert row.status == ListingStatus.ACTIVE.value


def test_one_source_failing_does_not_stop_another_source_succeeding():
    engine = _engine()
    parsers = {
        "vw": FailingParser(),
        "autoscout24": FakeParser("autoscout24", {"id4": [_raw("autoscout24", "9")], "id3": []}),
    }
    with Session(engine) as session:
        summary = run_crawl(session, parsers)
        assert summary.added == 1
        assert summary.failed_sources == ["vw"]


class FakeGeocoder:
    def __init__(self, coords_by_location):
        self._coords = coords_by_location
        self.calls: list[str] = []

    def geocode(self, location):
        self.calls.append(location)
        return self._coords.get(location)


def test_geocodes_a_new_listing_with_a_location():
    engine = _engine()
    geocoder = FakeGeocoder({"Berlin": (52.52, 13.40)})
    with Session(engine) as session:
        run_crawl(
            session,
            {"vw": FakeParser("vw", {"id4": [_raw("vw", "1")], "id3": []})},
            geocoder,
        )
        row = session.exec(select(Listing).where(Listing.source_id == "1")).one()
        assert row.latitude == 52.52
        assert row.longitude == 13.40


def test_no_geocoder_leaves_coordinates_null():
    engine = _engine()
    with Session(engine) as session:
        run_crawl(session, {"vw": FakeParser("vw", {"id4": [_raw("vw", "1")], "id3": []})})
        row = session.exec(select(Listing).where(Listing.source_id == "1")).one()
        assert row.latitude is None
        assert row.longitude is None


def test_geocoding_failure_leaves_coordinates_null():
    engine = _engine()
    geocoder = FakeGeocoder({})  # no known locations -> geocode() returns None for everything
    with Session(engine) as session:
        run_crawl(
            session,
            {"vw": FakeParser("vw", {"id4": [_raw("vw", "1", location="Nowhereville")], "id3": []})},
            geocoder,
        )
        row = session.exec(select(Listing).where(Listing.source_id == "1")).one()
        assert row.latitude is None
        assert geocoder.calls == ["Nowhereville"]


def test_reuses_cached_coordinates_for_a_repeated_location_within_one_crawl():
    engine = _engine()
    geocoder = FakeGeocoder({"Berlin": (52.52, 13.40)})
    with Session(engine) as session:
        run_crawl(
            session,
            {
                "vw": FakeParser(
                    "vw",
                    {
                        "id4": [_raw("vw", "1", location="Berlin"), _raw("vw", "2", location="Berlin")],
                        "id3": [],
                    },
                )
            },
            geocoder,
        )
        assert geocoder.calls == ["Berlin"]  # geocoded once, reused for the second listing
        rows = {r.source_id: r for r in session.exec(select(Listing)).all()}
        assert rows["1"].latitude == 52.52
        assert rows["2"].latitude == 52.52


def test_reuses_coordinates_already_known_in_the_db_without_calling_the_geocoder():
    engine = _engine()
    with Session(engine) as session:
        run_crawl(
            session,
            {"vw": FakeParser("vw", {"id4": [_raw("vw", "1", location="Berlin")], "id3": []})},
            FakeGeocoder({"Berlin": (52.52, 13.40)}),
        )

    # Second crawl, a different listing, same location string, with a geocoder
    # that has no known coordinates — proves the DB-known coordinate is reused
    # instead of calling the (here, failing) live geocoder.
    geocoder = FakeGeocoder({})
    with Session(engine) as session:
        run_crawl(
            session,
            {"vw": FakeParser("vw", {"id4": [_raw("vw", "2", location="Berlin")], "id3": []})},
            geocoder,
        )
        row = session.exec(select(Listing).where(Listing.source_id == "2")).one()
        assert row.latitude == 52.52
        assert geocoder.calls == []
