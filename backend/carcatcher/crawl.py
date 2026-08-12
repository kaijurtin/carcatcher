"""Crawl orchestration: fetch every source x model, upsert into `Listing`, mark
listings that disappeared from a source as `gone` — but only when that
source's fetch was both error-free and complete (see `FetchResult.complete`)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlmodel import Session, select

from carcatcher.db.models import Listing, ListingStatus
from carcatcher.geocoding import Geocoder
from carcatcher.scraping.base import Model, Parser, RawListing

logger = logging.getLogger(__name__)

# Bounds a single /refresh call's worst-case wall time against Nominatim's
# 1 request/second throttle. At 60, worst case adds ~60s — comfortably under
# both nginx's 120s proxy_read_timeout and Cloudflare's 100s 524 cutoff.
# Locations beyond the budget stay ungeocoded this crawl and are picked up
# on a later one, same as any other not-yet-geocoded location.
MAX_GEOCODES_PER_CRAWL = 60

MODELS: tuple[Model, ...] = ("id3", "id4")


@dataclass
class CrawlSummary:
    added: int = 0
    updated: int = 0
    gone: int = 0
    failed_sources: list[str] = field(default_factory=list)
    refreshed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def run_crawl(
    session: Session, parsers: dict[str, Parser], geocoder: Geocoder | None = None
) -> CrawlSummary:
    summary = CrawlSummary()
    seen_keys: set[tuple[str, str]] = set()
    succeeded_sources: set[str] = set()
    location_cache: dict[str, tuple[float, float] | None] = {}
    geocode_budget = [MAX_GEOCODES_PER_CRAWL]  # mutable single-element list: threaded by reference

    for name, parser in parsers.items():
        source_ok = True
        source_complete = True
        for model in MODELS:
            try:
                fetch_result = parser.fetch_listings(model)
            except Exception:
                logger.exception("crawl failed for source=%s model=%s", name, model)
                if name not in summary.failed_sources:
                    summary.failed_sources.append(name)
                source_ok = False
                continue
            if not fetch_result.complete:
                source_complete = False
            for raw in fetch_result.listings:
                seen_keys.add((raw.source, raw.source_id))
                listing, inserted = _upsert(session, raw)
                if inserted:
                    summary.added += 1
                else:
                    summary.updated += 1
                if geocoder is not None:
                    _resolve_coordinates(session, geocoder, location_cache, geocode_budget, raw, listing)
        # Only mark a source's un-seen listings `gone` when this crawl actually
        # covered all of it — a source-specific cap (e.g. a page limit) makes a
        # fetch `incomplete`, and un-seen listings from an incomplete fetch may
        # simply be ones the fetch never checked, not ones that vanished.
        if source_ok and source_complete:
            succeeded_sources.add(name)

    summary.gone = _mark_gone(session, succeeded_sources, seen_keys)
    session.commit()
    return summary


def _upsert(session: Session, raw: RawListing) -> tuple[Listing, bool]:
    """Insert or update the `Listing` row for `raw`. Returns (listing, True if
    newly inserted)."""
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
        existing.battery_kwh = raw.battery_kwh
        existing.condition = raw.condition
        if existing.location != raw.location:
            existing.latitude = None
            existing.longitude = None
        existing.location = raw.location
        existing.title = raw.title
        existing.status = ListingStatus.ACTIVE.value
        existing.last_seen_at = now
        session.add(existing)
        return existing, False
    listing = Listing(
        source=raw.source, source_id=raw.source_id, url=raw.url, model=raw.model,
        trim=raw.trim, price_eur=raw.price_eur, mileage_km=raw.mileage_km,
        year=raw.year, power_kw=raw.power_kw, battery_kwh=raw.battery_kwh,
        condition=raw.condition, location=raw.location, title=raw.title,
        status=ListingStatus.ACTIVE.value, first_seen_at=now, last_seen_at=now,
    )
    session.add(listing)
    return listing, True


def _resolve_coordinates(
    session: Session,
    geocoder: Geocoder,
    cache: dict[str, tuple[float, float] | None],
    budget: list[int],
    raw: RawListing,
    listing: Listing,
) -> None:
    """Fill `listing.latitude`/`longitude` from `raw.location`, reusing
    coordinates already known for that exact location string — first from
    this crawl's in-memory cache, then from any other listing already
    geocoded in the DB — before ever calling the live geocoder. Live calls
    are capped per crawl by `budget` (see MAX_GEOCODES_PER_CRAWL); once
    exhausted, unresolved locations are simply left for a later crawl."""
    if listing.latitude is not None and listing.longitude is not None:
        return
    if not raw.location:
        return
    if raw.location not in cache:
        known = _lookup_known_coordinates(session, raw.location)
        if known is not None:
            cache[raw.location] = known
        elif budget[0] > 0:
            budget[0] -= 1
            cache[raw.location] = geocoder.geocode(raw.location)
        else:
            return
    coords = cache[raw.location]
    if coords is not None:
        listing.latitude, listing.longitude = coords
        session.add(listing)


def _lookup_known_coordinates(session: Session, location: str) -> tuple[float, float] | None:
    row = session.exec(
        select(Listing.latitude, Listing.longitude)
        .where(
            Listing.location == location,
            Listing.latitude.is_not(None),
            Listing.longitude.is_not(None),
        )
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else None


def _mark_gone(
    session: Session, succeeded_sources: set[str], seen_keys: set[tuple[str, str]]
) -> int:
    """Mark `gone` any active listing whose source was crawled successfully AND
    completely this crawl but whose (source, source_id) wasn't seen. Listings
    from a failed or incomplete (capped) fetch are left alone — we have no
    evidence they actually disappeared, only that this fetch didn't check them."""
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
