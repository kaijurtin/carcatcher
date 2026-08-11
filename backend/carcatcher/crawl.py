"""Crawl orchestration: fetch every source x model, upsert into `Listing`, mark
listings that disappeared from a successfully-crawled source as `gone`."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlmodel import Session, select

from carcatcher.db.models import Listing, ListingStatus
from carcatcher.scraping.base import Model, Parser, RawListing

logger = logging.getLogger(__name__)

MODELS: tuple[Model, ...] = ("id3", "id4")


@dataclass
class CrawlSummary:
    added: int = 0
    updated: int = 0
    gone: int = 0
    failed_sources: list[str] = field(default_factory=list)
    refreshed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def run_crawl(session: Session, parsers: dict[str, Parser]) -> CrawlSummary:
    summary = CrawlSummary()
    seen_keys: set[tuple[str, str]] = set()
    succeeded_sources: set[str] = set()

    for name, parser in parsers.items():
        source_ok = True
        for model in MODELS:
            try:
                raw_listings = parser.fetch_listings(model)
            except Exception:
                logger.exception("crawl failed for source=%s model=%s", name, model)
                if name not in summary.failed_sources:
                    summary.failed_sources.append(name)
                source_ok = False
                continue
            for raw in raw_listings:
                seen_keys.add((raw.source, raw.source_id))
                if _upsert(session, raw):
                    summary.added += 1
                else:
                    summary.updated += 1
        if source_ok:
            succeeded_sources.add(name)

    summary.gone = _mark_gone(session, succeeded_sources, seen_keys)
    session.commit()
    return summary


def _upsert(session: Session, raw: RawListing) -> bool:
    """Insert or update the `Listing` row for `raw`. Returns True if newly inserted."""
    now = datetime.now(timezone.utc)
    existing = session.exec(
        select(Listing).where(Listing.source == raw.source, Listing.source_id == raw.source_id)
    ).first()
    if existing:
        existing.url = raw.url
        existing.model = raw.model
        existing.trim = raw.trim
        existing.price_eur = raw.price_eur
        existing.mileage_km = raw.mileage_km
        existing.year = raw.year
        existing.power_kw = raw.power_kw
        existing.condition = raw.condition
        existing.location = raw.location
        existing.title = raw.title
        existing.status = ListingStatus.ACTIVE.value
        existing.last_seen_at = now
        session.add(existing)
        return False
    session.add(
        Listing(
            source=raw.source, source_id=raw.source_id, url=raw.url, model=raw.model,
            trim=raw.trim, price_eur=raw.price_eur, mileage_km=raw.mileage_km,
            year=raw.year, power_kw=raw.power_kw, condition=raw.condition,
            location=raw.location, title=raw.title, status=ListingStatus.ACTIVE.value,
            first_seen_at=now, last_seen_at=now,
        )
    )
    return True


def _mark_gone(
    session: Session, succeeded_sources: set[str], seen_keys: set[tuple[str, str]]
) -> int:
    """Mark `gone` any active listing whose source completed this crawl but whose
    (source, source_id) wasn't seen. Listings from a failed source are left alone —
    we have no evidence they actually disappeared."""
    if not succeeded_sources:
        return 0
    active = session.exec(
        select(Listing).where(
            Listing.status == ListingStatus.ACTIVE.value,
            Listing.source.in_(succeeded_sources),  # type: ignore[union-attr]
        )
    ).all()
    count = 0
    for listing in active:
        if (listing.source, listing.source_id) not in seen_keys:
            listing.status = ListingStatus.GONE.value
            session.add(listing)
            count += 1
    return count
