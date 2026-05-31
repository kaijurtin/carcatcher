"""Normalize step: run Haiku over listings that need it (idempotent).

A listing needs normalization when `normalized_at` is None. The crawl step resets
that to None whenever the listing's content hash changes, so unchanged listings are
never re-normalized (no wasted Haiku calls). Failures record `normalization_error`
and mark the listing attempted so they are not retried until content changes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlmodel import Session, select

from carcatcher.config import get_settings
from carcatcher.db.models import Listing, ListingStatus, utcnow
from carcatcher.normalization.extractor import Extractor
from carcatcher.normalization.schema import NormalizedListing

# Haiku-derived fields that are always taken from the model.
_AI_FIELDS = (
    "make", "model", "variant", "fuel", "transmission",
    "power_kw", "body_type", "location_city", "location_plz", "seller_type",
)
# Deterministic card fields: trust the card; only fill if missing.
_FILL_IF_MISSING = ("price", "mileage_km", "year")


@dataclass
class NormalizeStats:
    normalized: int = 0
    failed: int = 0
    skipped: bool = False
    haiku_calls: int = 0
    cost_usd: float = 0.0


def apply_normalized(listing: Listing, norm: NormalizedListing) -> None:
    # Non-destructive: only overwrite when Haiku actually returned a value, so a
    # sparse extraction can never null out fields already populated by a scraper.
    for field in _AI_FIELDS:
        value = getattr(norm, field)
        if value is not None:
            setattr(listing, field, value)
    for field in _FILL_IF_MISSING:
        if getattr(listing, field) is None and getattr(norm, field) is not None:
            setattr(listing, field, getattr(norm, field))
    if listing.price is None and norm.price_negotiable:
        listing.price_negotiable = True
    listing.normalization_error = None
    listing.normalized_at = utcnow()


def _pending(session: Session, source: str | None, limit: int | None) -> list[Listing]:
    stmt = select(Listing).where(
        Listing.status == ListingStatus.ACTIVE.value,
        Listing.normalized_at.is_(None),  # type: ignore[union-attr]
    )
    if source:
        stmt = stmt.where(Listing.source == source)
    if limit:
        stmt = stmt.limit(limit)
    return list(session.exec(stmt).all())


async def normalize_pending(
    session: Session,
    extractor: Extractor,
    *,
    source: str | None = None,
    limit: int | None = None,
) -> NormalizeStats:
    """Normalize all active, not-yet-normalized listings. No-op if AI disabled."""
    stats = NormalizeStats()
    if not extractor.enabled:
        stats.skipped = True
        return stats

    listings = _pending(session, source, limit)
    if not listings:
        return stats

    sem = asyncio.Semaphore(max(1, get_settings().haiku_concurrency))

    async def work(listing: Listing):
        async with sem:
            try:
                norm, result = await extractor.extract(listing.raw_title, listing.raw_text)
                return listing, norm, result, None
            except Exception as exc:  # noqa: BLE001 — recorded per-listing
                return listing, None, None, exc

    results = await asyncio.gather(*(work(li) for li in listings))

    for listing, norm, result, error in results:
        if error is not None or norm is None:
            listing.normalization_error = str(error)[:500] if error else "unknown"
            listing.normalized_at = utcnow()  # mark attempted (don't retry-loop)
            stats.failed += 1
        else:
            apply_normalized(listing, norm)
            stats.normalized += 1
            stats.haiku_calls += 1
            stats.cost_usd += result.cost_usd
        session.add(listing)

    session.commit()
    return stats
