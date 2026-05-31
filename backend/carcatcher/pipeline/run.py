"""Crawl pipeline orchestration.

P1 implements the `crawl` step: stream stubs from a scraper and upsert them into
the Listing table (snapshot semantics). Normalization (P2), scoring (P4),
evaluation (P5), mark-gone + pruning (P3) layer on later.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from carcatcher.db.models import Listing, ListingStatus, utcnow
from carcatcher.scraping.base import ListingStub, Scraper, sha256_text
from carcatcher.schemas import StructuredFilters


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


def upsert_stub(session: Session, scraper: Scraper, stub: ListingStub) -> str:
    """Insert or update a Listing for `stub`. Returns "new" or "updated"."""
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
        return "new"

    old_hash = existing.raw_html_hash
    _apply_stub(existing, scraper, stub)
    if existing.raw_html_hash != old_hash:
        # Content changed → invalidate downstream AI/scoring so it recomputes.
        existing.normalized_at = None
        existing.scored_at = None
    session.add(existing)
    session.commit()
    return "updated"


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
        outcome = upsert_stub(session, scraper, stub)
        stats.seen += 1
        if outcome == "new":
            stats.new += 1
        else:
            stats.updated += 1
    return stats
