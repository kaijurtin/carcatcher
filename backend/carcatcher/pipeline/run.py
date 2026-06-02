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
    ListingSearch,
    ListingStatus,
    RunStatus,
    SavedSearch,
    utcnow,
)
from carcatcher.scraping.base import ListingStub, Scraper, sha256_text
from carcatcher.schemas import StructuredFilters, filters_from_criteria

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

    # Structured sources (e.g. AutoScout24) already provide clean fields — mark
    # normalized so Haiku is skipped (running it on sparse detail text would null
    # out the good data).
    if scraper.provides_structured_data and listing.make and listing.model:
        listing.normalized_at = utcnow()


def upsert_stub(session: Session, scraper: Scraper, stub: ListingStub) -> tuple[Listing, str]:
    """Insert or update a Listing for `stub`. Returns (listing, "new"|"updated")."""
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
        session.refresh(listing)
        return listing, "new"

    old_hash = existing.raw_html_hash
    _apply_stub(existing, scraper, stub)
    if existing.raw_html_hash != old_hash:
        # Content changed → invalidate downstream AI/scoring so it recomputes.
        existing.scored_at = None
        existing.ai_evaluated_at = None
        existing.ai_evaluation = None
        # Re-normalize only for unstructured sources; structured ones were just
        # re-marked normalized by _apply_stub.
        if not scraper.provides_structured_data:
            existing.normalized_at = None
    session.add(existing)
    session.commit()
    return existing, "updated"


def upsert_listing_search(session: Session, search_id: int, listing_id: int) -> None:
    """Tag a listing as belonging to a search (active + seen now)."""
    link = session.exec(
        select(ListingSearch).where(
            ListingSearch.search_id == search_id,
            ListingSearch.listing_id == listing_id,
        )
    ).first()
    now = utcnow()
    if link is None:
        link = ListingSearch(search_id=search_id, listing_id=listing_id)
    link.status = ListingStatus.ACTIVE.value
    link.last_seen_at = now
    session.add(link)
    session.commit()


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
        _, outcome = upsert_stub(session, scraper, stub)
        stats.seen += 1
        if outcome == "new":
            stats.new += 1
        else:
            stats.updated += 1
    return stats


async def crawl_search(session: Session, search: SavedSearch, state, settings) -> CrawlStats:
    """Crawl every source with one search's filters, tagging each listing with it."""
    filters = filters_from_criteria(search.criteria)
    stats = CrawlStats()
    for name, scraper in state.scrapers.items():
        try:
            async for stub in scraper.search(filters, max_pages=settings.search_max_pages):
                listing, outcome = upsert_stub(session, scraper, stub)
                upsert_listing_search(session, search.id, listing.id)
                stats.seen += 1
                if outcome == "new":
                    stats.new += 1
                else:
                    stats.updated += 1
        except Exception:  # noqa: BLE001 — one source failing shouldn't stop the search
            logger.exception("source %s failed for search %s", name, search.name)
    return stats


async def run_all_enabled(*, trigger: str = "scheduled") -> list[int]:
    """Run the full pipeline for every enabled saved search. Returns run ids."""
    with Session(get_engine()) as session:
        ids = [
            s.id
            for s in session.exec(
                select(SavedSearch).where(SavedSearch.enabled == True)  # noqa: E712
            ).all()
        ]
    out: list[int] = []
    for sid in ids:
        try:
            run_id = await run_search(sid, trigger=trigger)
        except Exception:  # noqa: BLE001 — one search failing shouldn't stop the rest
            logger.exception("search %s failed during scheduled crawl", sid)
            continue
        if run_id is not None:
            out.append(run_id)
    return out


async def run_search(search_id: int, *, trigger: str = "scheduled") -> int | None:
    """Full per-search pipeline: crawl (all sources, tagged) -> mark-gone (this search)
    -> recompute status -> normalize -> score -> evaluate -> prune, under a lock,
    recorded in a CrawlRun. Returns the run id, or None if skipped."""
    from carcatcher.app_state import get_state
    from carcatcher.pipeline.categorize import (
        AgentCategorizeStats,
        agent_categorize_active,
        categorize_active,
    )
    from carcatcher.pipeline.evaluate import EvalStats, evaluate_candidates
    from carcatcher.pipeline.normalize import NormalizeStats, normalize_pending
    from carcatcher.pipeline.score import score_active
    from carcatcher.settings_store import get_ai_enabled
    from carcatcher.pipeline.snapshot import (
        mark_gone_for_search,
        prune,
        recompute_listing_status,
        reclaim_stale_runs,
    )

    settings = get_settings()
    state = get_state()

    if state.crawl_lock.locked():
        logger.info("crawl already running — skipping %s trigger", trigger)
        return None

    async with state.crawl_lock:
        with Session(get_engine()) as session:
            reclaim_stale_runs(session, settings.run_timeout_minutes)
            search = session.get(SavedSearch, search_id)
            if search is None:
                return None
            run = CrawlRun(
                source=search.name,
                search_id=search_id,
                trigger=trigger,
                status=RunStatus.RUNNING.value,
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            run_id = run.id
            started = run.started_at

            try:
                ai_on = get_ai_enabled(session)  # dashboard toggle + env kill-switch
                crawl = await crawl_search(session, search, state, settings)
                gone = mark_gone_for_search(session, search_id, started)
                recompute_listing_status(session)
                # AI off -> skip Haiku/Sonnet entirely (zero tokens); the deterministic
                # categorizer below still fills make/model/variant/battery.
                norm = (
                    await normalize_pending(session, state.extractor)
                    if ai_on
                    else NormalizeStats(skipped=True)
                )
                categorize_active(session)  # P4.5: deterministic model rules, no AI
                # P4.6: guide-aware agent resolves variants left ambiguous above (VW
                # ID only, one Haiku call per ambiguous listing). Skipped with AI off.
                cat = (
                    await agent_categorize_active(session, state.guide_categorizer)
                    if ai_on
                    and settings.guide_categorizer_enabled
                    and state.guide_categorizer is not None
                    else AgentCategorizeStats(skipped=True)
                )
                score_active(session)
                ev = (
                    await evaluate_candidates(session, state.evaluator)
                    if ai_on
                    else EvalStats(skipped=True)
                )
                prune(session, settings.prune_gone_days)

                run = session.get(CrawlRun, run_id)
                run.listings_seen = crawl.seen
                run.listings_new = crawl.new
                run.listings_updated = crawl.updated
                run.listings_gone = gone
                run.haiku_calls = norm.haiku_calls + cat.haiku_calls
                run.sonnet_calls = ev.sonnet_calls
                run.est_cost_usd = round(norm.cost_usd + cat.cost_usd + ev.cost_usd, 6)
                run.status = RunStatus.DONE.value
                run.finished_at = utcnow()
                session.add(run)
                session.commit()
                logger.info(
                    "search '%s' run %s done: seen=%s new=%s gone=%s haiku=%s "
                    "guide_resolved=%s sonnet=%s cost=$%.4f",
                    search.name, run_id, crawl.seen, crawl.new, gone,
                    norm.haiku_calls + cat.haiku_calls, cat.resolved, ev.sonnet_calls,
                    norm.cost_usd + cat.cost_usd + ev.cost_usd,
                )
            except Exception as exc:  # noqa: BLE001 — recorded on the run
                logger.exception("search run %s failed", run_id)
                run = session.get(CrawlRun, run_id)
                run.status = RunStatus.FAILED.value
                run.error = str(exc)[:500]
                run.finished_at = utcnow()
                session.add(run)
                session.commit()
                raise

    return run_id
