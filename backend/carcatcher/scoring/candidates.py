"""Select which listings get the (paid) Sonnet evaluation — the cost-control gate.

A listing is a candidate if it is not yet evaluated AND either:
  - it passes the baseline (deal_score >= DEAL_THRESHOLD with enough comparables), OR
  - it is on the shortlist.
(Auto-evaluate SavedSearches join here in P7.) Ordered by best deal first and
capped at MAX_SONNET_EVALS_PER_RUN so a noisy run can't run up the bill.
"""

from __future__ import annotations

from sqlmodel import Session, select

from carcatcher.config import Settings
from carcatcher.db.models import Listing, ListingStatus, ShortlistItem


def select_candidates(session: Session, settings: Settings) -> list[Listing]:
    not_evaluated = Listing.ai_evaluated_at.is_(None)  # type: ignore[union-attr]
    active = Listing.status == ListingStatus.ACTIVE.value

    deal_candidates = session.exec(
        select(Listing).where(
            active,
            not_evaluated,
            Listing.deal_score.is_not(None),  # type: ignore[union-attr]
            Listing.deal_score >= settings.deal_threshold,
            Listing.comp_count >= settings.min_comps,
        )
    ).all()

    shortlist_ids = select(ShortlistItem.listing_id)
    shortlisted = session.exec(
        select(Listing).where(
            active,
            not_evaluated,
            Listing.id.in_(shortlist_ids),  # type: ignore[union-attr]
        )
    ).all()

    # Dedupe by id, keep highest deal_score first (None last), then cap.
    by_id: dict[int, Listing] = {}
    for listing in [*deal_candidates, *shortlisted]:
        by_id[listing.id] = listing
    ranked = sorted(
        by_id.values(),
        key=lambda x: x.deal_score if x.deal_score is not None else -1.0,
        reverse=True,
    )
    return ranked[: settings.max_sonnet_evals_per_run]
