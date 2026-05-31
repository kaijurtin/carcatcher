"""Per-search pipeline tests: run_search tags results, per-search mark-gone,
run_all_enabled honors the enabled flag, lock + failure handling."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlmodel import Session, select

from carcatcher.ai.client import AIClient
from carcatcher.ai.evaluate import Evaluator
from carcatcher.ai.nl_search import Translator
from carcatcher.ai.recommend import Recommender
from carcatcher.app_state import AppState, set_state
from carcatcher.config import Settings
from carcatcher.db.engine import get_engine
from carcatcher.db.models import (
    CrawlRun,
    Listing,
    ListingSearch,
    ListingStatus,
    RunStatus,
    SavedSearch,
    utcnow,
)
from carcatcher.normalization.extractor import Extractor
from carcatcher.pipeline.run import run_all_enabled, run_search
from carcatcher.scraping.kleinanzeigen import KleinanzeigenScraper
from tests.fakes import FakeFirecrawl


@pytest.fixture()
def state():
    fc = FakeFirecrawl()
    ai = AIClient(Settings(ai_disabled=True))
    st = AppState(
        firecrawl=fc,
        scrapers={"kleinanzeigen": KleinanzeigenScraper(fc)},
        ai=ai,
        extractor=Extractor(ai),
        evaluator=Evaluator(ai),
        translator=Translator(ai),
        recommender=Recommender(ai),
    )
    set_state(st)
    yield st
    set_state(None)


def _new_search(name="Golf", **criteria) -> int:
    with Session(get_engine()) as s:
        ss = SavedSearch(name=name, criteria=criteria)
        s.add(ss)
        s.commit()
        s.refresh(ss)
        return ss.id


async def test_run_search_tags_results(test_engine, state):
    sid = _new_search()
    run_id = await run_search(sid, trigger="manual")
    assert run_id is not None
    with Session(get_engine()) as s:
        run = s.get(CrawlRun, run_id)
        assert run.status == RunStatus.DONE.value
        assert run.search_id == sid
        assert run.source == "Golf"
        listings = s.exec(select(Listing)).all()
        links = s.exec(select(ListingSearch)).all()
        assert len(listings) == 3
        assert len(links) == 3  # each listing tagged with the search
        assert all(li.search_id == sid and li.status == "active" for li in links)


async def test_run_search_marks_only_its_links_gone(test_engine, state):
    sid = _new_search()
    # Pre-existing link to a listing this crawl won't re-see → should go gone.
    with Session(get_engine()) as s:
        stale = Listing(source="kleinanzeigen", source_id="999", url="old")
        s.add(stale)
        s.commit()
        s.refresh(stale)
        s.add(ListingSearch(search_id=sid, listing_id=stale.id,
                            status="active", last_seen_at=utcnow() - timedelta(days=1)))
        s.commit()

    await run_search(sid, trigger="manual")

    with Session(get_engine()) as s:
        stale = s.exec(select(Listing).where(Listing.source_id == "999")).one()
        link = s.exec(
            select(ListingSearch).where(ListingSearch.listing_id == stale.id)
        ).one()
        assert link.status == ListingStatus.GONE.value


async def test_run_search_skips_when_locked(test_engine, state):
    sid = _new_search()
    await state.crawl_lock.acquire()
    try:
        assert await run_search(sid, trigger="scheduled") is None
    finally:
        state.crawl_lock.release()


async def test_run_all_enabled_only_runs_enabled(test_engine, state):
    with Session(get_engine()) as s:
        s.add_all([
            SavedSearch(name="on", criteria={}, enabled=True),
            SavedSearch(name="off", criteria={}, enabled=False),
        ])
        s.commit()
    ids = await run_all_enabled(trigger="scheduled")
    assert len(ids) == 1  # only the enabled search ran
    with Session(get_engine()) as s:
        runs = s.exec(select(CrawlRun)).all()
        assert {r.source for r in runs} == {"on"}


async def test_run_search_swallows_source_errors(test_engine, state):
    class BoomScraper(KleinanzeigenScraper):
        async def search(self, *a, **k):
            raise RuntimeError("scrape boom")
            yield  # pragma: no cover

    # crawl_search swallows per-source errors, so the run still completes (done,
    # zero results) rather than crashing the whole search.
    state.scrapers["kleinanzeigen"] = BoomScraper(FakeFirecrawl())
    sid = _new_search()
    run_id = await run_search(sid, trigger="manual")
    with Session(get_engine()) as s:
        run = s.get(CrawlRun, run_id)
        assert run.status == RunStatus.DONE.value
        assert run.listings_seen == 0
