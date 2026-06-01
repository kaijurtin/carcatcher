"""Crawl pipeline tests: scraper.search over a fake Firecrawl + upsert semantics."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, select

from carcatcher.db.engine import get_engine
from carcatcher.db.models import Listing
from carcatcher.pipeline.categorize import categorize_active
from carcatcher.pipeline.run import crawl_source
from carcatcher.scraping.kleinanzeigen import KleinanzeigenScraper
from carcatcher.schemas import StructuredFilters

FIXTURE = Path(__file__).parent / "fixtures" / "kleinanzeigen_search.html"


class FakeFirecrawl:
    """Returns the fixture HTML for the first page, then empty (pagination stop)."""

    def __init__(self) -> None:
        self.calls = 0

    async def scrape(self, url: str, *, formats=None, only_main_content=True) -> dict:
        self.calls += 1
        if self.calls == 1:
            return {"html": FIXTURE.read_text(encoding="utf-8")}
        return {"html": ""}


@pytest.fixture()
def scraper() -> KleinanzeigenScraper:
    return KleinanzeigenScraper(firecrawl=FakeFirecrawl())  # type: ignore[arg-type]


async def test_crawl_inserts_sales_only(test_engine, scraper):
    with Session(get_engine()) as session:
        stats = await crawl_source(
            session, scraper, StructuredFilters(), max_pages=5
        )
        assert stats.new == 3  # Gesuch excluded
        assert stats.seen == 3
        rows = session.exec(select(Listing)).all()
        assert len(rows) == 3
        assert any(r.price for r in rows)
        assert any(r.year for r in rows)


async def test_pagination_stops_on_empty_page(test_engine, scraper):
    with Session(get_engine()) as session:
        await crawl_source(session, scraper, StructuredFilters(), max_pages=5)
    # page 1 -> fixture, page 2 -> empty => exactly 2 scrape calls
    assert scraper._fc.calls == 2  # type: ignore[attr-defined]


async def test_recrawl_updates_not_duplicates(test_engine):
    with Session(get_engine()) as session:
        s1 = KleinanzeigenScraper(firecrawl=FakeFirecrawl())  # type: ignore[arg-type]
        await crawl_source(session, s1, StructuredFilters(), max_pages=1)
        s2 = KleinanzeigenScraper(firecrawl=FakeFirecrawl())  # type: ignore[arg-type]
        stats2 = await crawl_source(session, s2, StructuredFilters(), max_pages=1)
        assert stats2.updated == 3
        assert stats2.new == 0
        assert len(session.exec(select(Listing)).all()) == 3


def test_categorize_active_fills_vw_id_when_ai_off(test_engine):
    # AI-off shape: only the card fields + raw title are present (make/model None).
    with Session(get_engine()) as session:
        session.add(
            Listing(
                source="kleinanzeigen", source_id="k1", url="k1",
                raw_title="VW ID.4 GTX 4MOTION", year=2023,
            )
        )
        session.commit()

        stats = categorize_active(session)
        assert stats.categorized == 1

        li = session.exec(select(Listing)).one()
        assert (li.make, li.model, li.variant, li.battery_kwh) == (
            "Volkswagen", "ID.4", "GTX", 77.0,
        )

        # Idempotent: a second pass changes nothing.
        assert categorize_active(session).categorized == 0
