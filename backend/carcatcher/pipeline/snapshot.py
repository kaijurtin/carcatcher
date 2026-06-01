"""Snapshot maintenance: mark-gone, prune, and stale-run reclamation.

Snapshot semantics (current-snapshot-only, no history): after a *successful* full
crawl of a source, any active listing of that source not seen this run is `gone`
(sold/removed). Stale `gone` rows that nothing references are eventually pruned.
Shortlisted listings are never hard-deleted.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlmodel import Session, select

from carcatcher.db.models import (
    CrawlRun,
    Favorite,
    Listing,
    ListingSearch,
    ListingStatus,
    RunStatus,
    ShortlistItem,
    utcnow,
)


def mark_gone_for_search(
    session: Session, search_id: int, run_started_at: datetime
) -> int:
    """Mark this search's links not seen since `run_started_at` as gone. Per-search,
    so one search's crawl never affects another search's listings."""
    stale = session.exec(
        select(ListingSearch).where(
            ListingSearch.search_id == search_id,
            ListingSearch.status == ListingStatus.ACTIVE.value,
            ListingSearch.last_seen_at < run_started_at,
        )
    ).all()
    for link in stale:
        link.status = ListingStatus.GONE.value
        session.add(link)
    session.commit()
    return len(stale)


def recompute_listing_status(session: Session) -> None:
    """A Listing is active iff at least one of its search links is active."""
    active_ids = {
        row
        for row in session.exec(
            select(ListingSearch.listing_id).where(
                ListingSearch.status == ListingStatus.ACTIVE.value
            )
        ).all()
    }
    for listing in session.exec(select(Listing)).all():
        listing.status = (
            ListingStatus.ACTIVE.value
            if listing.id in active_ids
            else ListingStatus.GONE.value
        )
        session.add(listing)
    session.commit()


def prune(session: Session, prune_gone_days: int) -> int:
    """Delete gone links older than the cutoff, then delete orphan Listings (no links)
    that no ShortlistItem or Favorite references. Shortlisted and favorited listings
    always survive."""
    cutoff = utcnow() - timedelta(days=prune_gone_days)
    session.exec(  # type: ignore[call-overload]
        delete(ListingSearch)
        .where(
            ListingSearch.status == ListingStatus.GONE.value,
            ListingSearch.last_seen_at < cutoff,
        )
        .execution_options(synchronize_session=False)
    )
    session.commit()

    linked = select(ListingSearch.listing_id).distinct()
    shortlisted = select(ShortlistItem.listing_id)
    favorited = select(Favorite.listing_id)
    result = session.exec(  # type: ignore[call-overload]
        delete(Listing)
        .where(
            Listing.id.not_in(linked),  # type: ignore[union-attr]
            Listing.id.not_in(shortlisted),  # type: ignore[union-attr]
            Listing.id.not_in(favorited),  # type: ignore[union-attr]
        )
        .execution_options(synchronize_session=False)
    )
    session.commit()
    return result.rowcount or 0


def reclaim_stale_runs(session: Session, timeout_minutes: int) -> int:
    """Fail any `running` CrawlRun older than the timeout (e.g. crashed mid-run)."""
    cutoff = utcnow() - timedelta(minutes=timeout_minutes)
    stale = session.exec(
        select(CrawlRun).where(
            CrawlRun.status == RunStatus.RUNNING.value,
            CrawlRun.started_at < cutoff,
        )
    ).all()
    for run in stale:
        run.status = RunStatus.FAILED.value
        run.error = "reclaimed: exceeded run timeout"
        run.finished_at = utcnow()
        session.add(run)
    session.commit()
    return len(stale)


def is_crawl_running(session: Session) -> bool:
    """True if a (non-stale) CrawlRun is currently running."""
    run = session.exec(
        select(CrawlRun).where(CrawlRun.status == RunStatus.RUNNING.value)
    ).first()
    return run is not None
