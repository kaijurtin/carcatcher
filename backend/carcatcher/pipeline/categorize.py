"""Categorize step: apply deterministic model rules over active listings (no AI).

Runs unconditionally on every pass — it is pure Python (zero cost) and idempotent,
so there is no `categorized_at` bookkeeping. It also self-heals: updating the
reference data re-canonicalizes existing rows on the next crawl. With AI on it only
canonicalizes/gap-fills Haiku output; with AI off it is the sole structured-field
provider, so the dashboard still shows and sorts model/variant/battery.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlmodel import Session, select

from carcatcher.db.models import Listing, ListingStatus
from carcatcher.normalization.guide_categorizer import (
    GuideCategorizer,
    apply_agent_variant,
    is_ambiguous_vw_id,
)
from carcatcher.normalization.guide_loader import GuideKnowledge, load_guide_knowledge
from carcatcher.normalization.model_categorizer import apply_categorization

logger = logging.getLogger(__name__)


@dataclass
class CategorizeStats:
    categorized: int = 0


@dataclass
class AgentCategorizeStats:
    resolved: int = 0
    haiku_calls: int = 0
    cost_usd: float = 0.0
    skipped: bool = False


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


async def agent_categorize_active(
    session: Session, categorizer: GuideCategorizer
) -> AgentCategorizeStats:
    """Resolve variants for VW ID listings the deterministic step left ambiguous.

    Runs only on rows where a VW ID model is recognized but no variant resolved (and a
    guide exists). One Haiku call per such listing; guide knowledge is loaded once per
    model. Non-destructive and a no-op when AI is unavailable.
    """
    stats = AgentCategorizeStats()
    if not categorizer.enabled:
        stats.skipped = True
        return stats

    listings = session.exec(
        select(Listing).where(Listing.status == ListingStatus.ACTIVE.value)
    ).all()
    guide_cache: dict[tuple[str, str], GuideKnowledge | None] = {}
    changed = False
    for listing in listings:
        if not is_ambiguous_vw_id(listing):
            continue
        key = (listing.make or "", listing.model or "")
        if key not in guide_cache:
            guide_cache[key] = load_guide_knowledge(key[0], key[1])
        knowledge = guide_cache[key]
        if knowledge is None:
            continue
        try:
            result, struct = await categorizer.categorize(listing, knowledge)
        except Exception:  # noqa: BLE001 — one listing failing shouldn't stop the rest
            logger.exception("guide categorizer failed for listing %s", listing.id)
            continue
        stats.haiku_calls += 1
        stats.cost_usd += struct.cost_usd
        if apply_agent_variant(listing, result):
            session.add(listing)
            stats.resolved += 1
            changed = True
    if changed:
        session.commit()
    return stats
