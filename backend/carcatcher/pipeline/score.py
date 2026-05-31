"""Score step: recompute the fair-price baseline for the current snapshot.

Because adding/removing listings changes the comparable set, every active listing is
re-scored each run. Runs after mark-gone so stale listings don't pollute comparables.
No AI — pure statistics, always runs even when AI is disabled.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from carcatcher.config import get_settings
from carcatcher.db.models import Listing, ListingStatus
from carcatcher.scoring.baseline import score_listing


@dataclass
class ScoreStats:
    scored: int = 0
    with_estimate: int = 0
    deals: int = 0


def score_active(session: Session, *, source: str | None = None) -> ScoreStats:
    settings = get_settings()
    stmt = select(Listing).where(Listing.status == ListingStatus.ACTIVE.value)
    if source:
        stmt = stmt.where(Listing.source == source)
    listings = list(session.exec(stmt).all())

    stats = ScoreStats()
    for listing in listings:
        result = score_listing(session, listing, min_comps=settings.min_comps)
        stats.scored += 1
        if result.fair_price_estimate is not None:
            stats.with_estimate += 1
        if result.deal_score is not None and result.deal_score >= settings.deal_threshold:
            stats.deals += 1
    session.commit()
    return stats
