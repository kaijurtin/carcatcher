"""Full run_pipeline tests: orchestration, lock, mark-gone, CrawlRun lifecycle."""

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
from carcatcher.db.models import CrawlRun, Listing, ListingStatus, RunStatus, utcnow
from carcatcher.normalization.extractor import Extractor
from carcatcher.pipeline.run import run_pipeline
from carcatcher.scraping.kleinanzeigen import KleinanzeigenScraper
from tests.fakes import FakeFirecrawl


@pytest.fixture()
def state():
    fc = FakeFirecrawl()
    scraper = KleinanzeigenScraper(fc)
    ai = AIClient(Settings(ai_disabled=True))  # no AI in this test
    st = AppState(
        firecrawl=fc,
        scrapers={"kleinanzeigen": scraper},
        ai=ai,
        extractor=Extractor(ai),
        evaluator=Evaluator(ai),
        translator=Translator(ai),
        recommender=Recommender(ai),
    )
    set_state(st)
    yield st
    set_state(None)


async def test_run_pipeline_crawls_and_finalizes(test_engine, state):
    run_id = await run_pipeline(source="kleinanzeigen", trigger="manual")
    assert run_id is not None
    with Session(get_engine()) as s:
        run = s.get(CrawlRun, run_id)
        assert run.status == RunStatus.DONE.value
        assert run.listings_new == 3
        assert run.trigger == "manual"
        assert len(s.exec(select(Listing)).all()) == 3


async def test_run_pipeline_marks_unseen_gone(test_engine, state):
    # Seed a stale active listing that won't appear in this crawl.
    with Session(get_engine()) as s:
        s.add(Listing(source="kleinanzeigen", source_id="999999", url="old",
                      status=ListingStatus.ACTIVE.value,
                      last_seen_at=utcnow() - timedelta(days=1)))
        s.commit()

    await run_pipeline(source="kleinanzeigen", trigger="manual")

    with Session(get_engine()) as s:
        stale = s.exec(
            select(Listing).where(Listing.source_id == "999999")
        ).one()
        assert stale.status == ListingStatus.GONE.value


async def test_run_pipeline_skips_when_locked(test_engine, state):
    await state.crawl_lock.acquire()
    try:
        result = await run_pipeline(source="kleinanzeigen", trigger="scheduled")
        assert result is None  # already locked → skipped
    finally:
        state.crawl_lock.release()


async def test_run_pipeline_records_failure(test_engine, state):
    class BoomScraper(KleinanzeigenScraper):
        async def search(self, *a, **k):
            raise RuntimeError("scrape boom")
            yield  # pragma: no cover

    state.scrapers["kleinanzeigen"] = BoomScraper(FakeFirecrawl())
    with pytest.raises(RuntimeError):
        await run_pipeline(source="kleinanzeigen", trigger="manual")

    with Session(get_engine()) as s:
        run = s.exec(select(CrawlRun)).one()
        assert run.status == RunStatus.FAILED.value
        assert "boom" in (run.error or "")
