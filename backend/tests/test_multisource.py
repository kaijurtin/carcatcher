"""Multi-source behavior: AS24 __NEXT_DATA__ seeds the card; the agent normalizes later."""

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, select

from carcatcher.db.engine import get_engine
from carcatcher.db.models import Listing
from carcatcher.pipeline.run import crawl_source
from carcatcher.scraping.autoscout24 import AutoScout24Scraper
from carcatcher.scraping.registry import build_registry
from carcatcher.schemas import StructuredFilters

AS24_FIXTURE = Path(__file__).parent / "fixtures" / "autoscout24_search.html"


class FakeAS24Firecrawl:
    def __init__(self) -> None:
        self.calls = 0

    async def scrape(self, url, *, formats=None, only_main_content=True) -> dict:
        self.calls += 1
        if self.calls == 1:
            return {"html": AS24_FIXTURE.read_text(encoding="utf-8")}
        return {"html": ""}


def test_registry_has_all_three_sources():
    reg = build_registry(firecrawl=None)  # type: ignore[arg-type]
    assert set(reg) == {"kleinanzeigen", "autoscout24", "mobilede"}


async def test_as24_crawl_seeds_fields_but_defers_normalization(test_engine):
    scraper = AutoScout24Scraper(FakeAS24Firecrawl())  # type: ignore[arg-type]
    with Session(get_engine()) as s:
        stats = await crawl_source(s, scraper, StructuredFilters(), max_pages=3)
        assert stats.new == 3
        rows = s.exec(select(Listing)).all()
        # __NEXT_DATA__ seeds make/model via basic_specs, but normalization is deferred
        # to the agent (normalized_at stays None until P2 runs).
        assert all(r.make and r.model for r in rows)
        assert all(r.normalized_at is None for r in rows)
        assert all(r.source == "autoscout24" for r in rows)
