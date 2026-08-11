"""SQLModel tables for CarCatcher.

Snapshot semantics: listings are upserted by (source, source_id) on every crawl.
A listing not seen in a successful crawl of its own source is marked `gone`. There
is no price history — the current set of `active` rows IS the snapshot.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Timezone-aware UTC now (avoids deprecated datetime.utcnow)."""
    return datetime.now(timezone.utc)


class ListingStatus(str, enum.Enum):
    ACTIVE = "active"
    GONE = "gone"


class Listing(SQLModel, table=True):
    __tablename__ = "listing"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_listing_source"),)

    id: int | None = Field(default=None, primary_key=True)

    source: str = Field(index=True)  # "autoscout24" | "vw"
    source_id: str
    url: str
    model: str = Field(index=True)  # "id3" | "id4"
    trim: str = ""
    price_eur: int | None = Field(default=None, index=True)
    mileage_km: int | None = None
    year: int | None = None
    power_kw: int | None = None
    condition: str = "used"  # "new" | "used"
    location: str | None = None
    title: str = ""

    status: str = Field(default=ListingStatus.ACTIVE.value, index=True)
    first_seen_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow, index=True)
