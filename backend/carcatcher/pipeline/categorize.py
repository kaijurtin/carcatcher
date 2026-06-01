"""Categorize step: apply deterministic model rules over active listings (no AI).

Runs unconditionally on every pass — it is pure Python (zero cost) and idempotent,
so there is no `categorized_at` bookkeeping. It also self-heals: updating the
reference data re-canonicalizes existing rows on the next crawl. With AI on it only
canonicalizes/gap-fills Haiku output; with AI off it is the sole structured-field
provider, so the dashboard still shows and sorts model/variant/battery.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from carcatcher.db.models import Listing, ListingStatus
from carcatcher.normalization.model_categorizer import apply_categorization


@dataclass
class CategorizeStats:
    categorized: int = 0


def categorize_active(session: Session) -> CategorizeStats:
    """Apply the model categorizer to every active listing. Returns counts."""
    stats = CategorizeStats()
    listings = session.exec(
        select(Listing).where(Listing.status == ListingStatus.ACTIVE.value)
    ).all()
    for listing in listings:
        if apply_categorization(listing):
            session.add(listing)
            stats.categorized += 1
    if stats.categorized:
        session.commit()
    return stats
