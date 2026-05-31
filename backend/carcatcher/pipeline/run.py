"""Crawl pipeline orchestration.

P1 implements the `crawl` step: stream stubs from a scraper and upsert them into
the Listing table (snapshot semantics). Normalization (P2), scoring (P4),
evaluation (P5), mark-gone + pruning (P3) layer on later.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlmodel import Session, select

from carcatcher.config import get_settings
from carcatcher.db.engine import get_engine
from carcatcher.db.models import (
    CrawlRun,
    Listing,
    ListingStatus,
    RunStatus,
    SavedSearch,
    utcnow,
)
from carcatcher.scraping.base import ListingStub, Scraper, sha256_text
from carcatcher.schemas import StructuredFilters

logger = logging.getLogger(__name__)


@dataclass
class CrawlStats:
    seen: int = 0
    new: int = 0
    updated: int = 0


def _apply_stub(listing: Listing, scraper: Scraper, stub: ListingStub) -> None:
    """Copy raw + cheap-card fields from a stub onto a Listing row."""
    listing.url = stub.url
    listing.raw_title = stub.title
    listing.raw_price = stub.price_hint
    listing.raw_text = stub.description_hint or ""
    listing.location_raw = stub.location_hint
    listing.images = [stub.image_hint] if stub.image_hint else []
    listing.status = ListingStatus.ACTIVE.value
    listing.last_seen_at = utcnow()
    listing.scraped_at = utcnow()
    listing.raw_html_hash = sha256_text(f"{stub.title}\n{stub.description_hint or ''}")

    # Deterministic card specs (price/mileage/year) — not AI normalization.
    for key, value in scraper.basic_specs(stub).items():
        setattr(listing, key, value)


def upsert_stub(session: Session, scraper: Scraper, stub: ListingStub) -> str:
    """Insert or update a Listing for `stub`. Returns "new" or "updated"."""
    existing = session.exec(
        select(Listing).where(
            Listing.source == stub.source, Listing.source_id == stub.source_id
        )
    ).first()

    if existing is None:
        listing = Listing(source=stub.source, source_id=stub.source_id, url=stub.url)
        _apply_stub(listing, scraper, stub)
        session.add(listing)
        session.commit()
        return "new"

    old_hash = existing.raw_html_hash
    _apply_stub(existing, scraper, stub)
    if existing.raw_html_hash != old_hash:
        # Content changed → invalidate downstream AI/scoring so it recomputes.
        existing.normalized_at = None
        existing.scored_at = None
    session.add(existing)
    session.commit()
    return "updated"


async def crawl_source(
    session: Session,
    scraper: Scraper,
    filters: StructuredFilters,
    *,
    max_pages: int,
) -> CrawlStats:
    """Run one source's search and upsert every stub. Returns crawl counts."""
    stats = CrawlStats()
    async for stub in scraper.search(filters, max_pages=max_pages):
        outcome = upsert_stub(session, scraper, stub)
        stats.seen += 1
        if outcome == "new":
            stats.new += 1
        else:
            stats.updated += 1
    return stats


def _filters_from_criteria(criteria: dict) -> StructuredFilters:
    fields = StructuredFilters.model_fields
    return StructuredFilters(**{k: v for k, v in criteria.items() if k in fields})


def build_searches(session: Session) -> list[StructuredFilters]:
    """The searches a crawl runs: every SavedSearch plus a default broad sweep."""
    searches = [StructuredFilters()]  # broad "all autos" baseline
    for ss in session.exec(select(SavedSearch)).all():
        searches.append(_filters_from_criteria(ss.criteria))
    return searches


async def run_pipeline(*, source: str = "kleinanzeigen", trigger: str = "scheduled") -> int | None:
    """Full crawl run: crawl -> normalize -> mark-gone -> prune, under a lock,
    recorded in a CrawlRun. Returns the run id, or None if a crawl is already
    in flight. Imports are local to avoid an app_state import cycle."""
    from carcatcher.app_state import get_state
    from carcatcher.pipeline.normalize import normalize_pending
    from carcatcher.pipeline.snapshot import mark_gone, prune_gone, reclaim_stale_runs

    settings = get_settings()
    state = get_state()

    if state.crawl_lock.locked():
        logger.info("crawl already running — skipping %s trigger", trigger)
        return None

    async with state.crawl_lock:
        with Session(get_engine()) as session:
            reclaim_stale_runs(session, settings.run_timeout_minutes)
            run = CrawlRun(source=source, trigger=trigger, status=RunStatus.RUNNING.value)
            session.add(run)
            session.commit()
            session.refresh(run)
            run_id = run.id
            started = run.started_at

            try:
                scraper = state.scrapers[source]
                crawl = CrawlStats()
                for filters in build_searches(session):
                    s = await crawl_source(
                        session, scraper, filters, max_pages=settings.search_max_pages
                    )
                    crawl.seen += s.seen
                    crawl.new += s.new
                    crawl.updated += s.updated

                norm = await normalize_pending(session, state.extractor, source=source)
                gone = mark_gone(session, source, started)
                prune_gone(session, settings.prune_gone_days)

                run = session.get(CrawlRun, run_id)
                run.listings_seen = crawl.seen
                run.listings_new = crawl.new
                run.listings_updated = crawl.updated
                run.listings_gone = gone
                run.haiku_calls = norm.haiku_calls
                run.est_cost_usd = round(norm.cost_usd, 6)
                run.status = RunStatus.DONE.value
                run.finished_at = utcnow()
                session.add(run)
                session.commit()
                logger.info(
                    "crawl %s done: seen=%s new=%s gone=%s haiku=%s cost=$%.4f",
                    run_id, crawl.seen, crawl.new, gone, norm.haiku_calls, norm.cost_usd,
                )
            except Exception as exc:  # noqa: BLE001 — recorded on the run
                logger.exception("crawl %s failed", run_id)
                run = session.get(CrawlRun, run_id)
                run.status = RunStatus.FAILED.value
                run.error = str(exc)[:500]
                run.finished_at = utcnow()
                session.add(run)
                session.commit()
                raise

    return run_id
