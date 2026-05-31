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
    Listing,
    ListingStatus,
    RunStatus,
    ShortlistItem,
    utcnow,
)


def mark_gone(session: Session, source: str, run_started_at: datetime) -> int:
    """Mark active listings of `source` not seen since `run_started_at` as gone.
    Call ONLY after a successful full crawl of that source."""
    stale = session.exec(
        select(Listing).where(
            Listing.source == source,
            Listing.status == ListingStatus.ACTIVE.value,
            Listing.last_seen_at < run_started_at,
        )
    ).all()
    for listing in stale:
        listing.status = ListingStatus.GONE.value
        session.add(listing)
    session.commit()
    return len(stale)


def prune_gone(session: Session, prune_gone_days: int) -> int:
    """Delete `gone` listings older than the cutoff that no ShortlistItem references."""
    cutoff = utcnow() - timedelta(days=prune_gone_days)
    referenced = select(ShortlistItem.listing_id)
    result = session.exec(  # type: ignore[call-overload]
        delete(Listing)
        .where(
            Listing.status == ListingStatus.GONE.value,
            Listing.last_seen_at < cutoff,
            Listing.id.not_in(referenced),  # type: ignore[union-attr]
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
