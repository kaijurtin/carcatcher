"""SQLModel tables for CarCatcher.

Snapshot semantics: listings are upserted by (source, source_id) on every crawl.
After a successful full crawl, listings of that source not seen this run are marked
`gone`; stale unreferenced `gone` rows are later pruned. There is no price history —
the current set of `active` rows IS the snapshot.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, Index, SQLModel


def utcnow() -> datetime:
    """Timezone-aware UTC now (avoids deprecated datetime.utcnow)."""
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enums (stored as plain strings for SQLite friendliness)
# --------------------------------------------------------------------------- #
class ListingStatus(str, enum.Enum):
    ACTIVE = "active"
    GONE = "gone"
    ERROR = "error"


class Fuel(str, enum.Enum):
    PETROL = "petrol"
    DIESEL = "diesel"
    HYBRID = "hybrid"
    ELECTRIC = "electric"
    LPG = "lpg"
    CNG = "cng"
    OTHER = "other"


class Transmission(str, enum.Enum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"


class SellerType(str, enum.Enum):
    PRIVATE = "private"
    DEALER = "dealer"


class RunStatus(str, enum.Enum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


# --------------------------------------------------------------------------- #
# Listing
# --------------------------------------------------------------------------- #
class Listing(SQLModel, table=True):
    __tablename__ = "listing"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_listing_source"),
        Index("ix_listing_snapshot", "source", "make", "model", "status"),
    )

    id: int | None = Field(default=None, primary_key=True)

    # --- identity / dedup ---
    source: str = Field(index=True)  # kleinanzeigen / autoscout24 / mobilede
    source_id: str
    url: str
    status: str = Field(default=ListingStatus.ACTIVE.value, index=True)

    # --- raw (as scraped) ---
    raw_title: str = ""
    raw_text: str = ""
    raw_price: str | None = None
    raw_html_hash: str = ""  # sha256 of rendered content, for idempotency
    images: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    location_raw: str | None = None

    # --- normalized (Haiku) ---
    price: int | None = Field(default=None, index=True)
    price_negotiable: bool = False
    mileage_km: int | None = None
    year: int | None = None
    make: str | None = Field(default=None, index=True)
    model: str | None = Field(default=None, index=True)
    variant: str | None = None
    fuel: str | None = None
    transmission: str | None = None
    power_kw: int | None = None
    battery_kwh: float | None = None  # EV usable battery capacity (electric/hybrid only)
    battery_soh_pct: int | None = None  # EV battery State of Health 0-100
    body_type: str | None = None
    location_city: str | None = None
    location_plz: str | None = None
    seller_type: str | None = None
    normalization_error: str | None = None

    # --- scoring ---
    fair_price_estimate: int | None = None
    deal_score: float | None = Field(default=None, index=True)
    comp_count: int | None = None

    # --- AI evaluation (Sonnet) ---
    ai_evaluation: dict | None = Field(default=None, sa_column=Column(JSON))
    ai_evaluated_at: datetime | None = None

    # --- timestamps ---
    first_seen_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow, index=True)
    scraped_at: datetime = Field(default_factory=utcnow)
    normalized_at: datetime | None = None
    scored_at: datetime | None = None


# --------------------------------------------------------------------------- #
# SavedSearch
# --------------------------------------------------------------------------- #
class SavedSearch(SQLModel, table=True):
    __tablename__ = "saved_search"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    criteria: dict = Field(default_factory=dict, sa_column=Column(JSON))
    nl_query: str | None = None
    auto_evaluate: bool = False
    enabled: bool = True  # whether it runs on the scheduled crawl
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- #
# ListingSearch — many-to-many link tagging a listing with the search(es) that
# found it, with a per-search snapshot status (so one search's crawl never
# marks another search's listings gone).
# --------------------------------------------------------------------------- #
class ListingSearch(SQLModel, table=True):
    __tablename__ = "listing_search"
    __table_args__ = (
        UniqueConstraint("search_id", "listing_id", name="uq_listing_search"),
    )

    id: int | None = Field(default=None, primary_key=True)
    search_id: int = Field(foreign_key="saved_search.id", index=True)
    listing_id: int = Field(foreign_key="listing.id", index=True)
    status: str = Field(default=ListingStatus.ACTIVE.value, index=True)
    first_seen_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow, index=True)


# --------------------------------------------------------------------------- #
# Shortlist
# --------------------------------------------------------------------------- #
class Shortlist(SQLModel, table=True):
    __tablename__ = "shortlist"

    id: int | None = Field(default=None, primary_key=True)
    name: str = "default"
    created_at: datetime = Field(default_factory=utcnow)


class ShortlistItem(SQLModel, table=True):
    __tablename__ = "shortlist_item"
    __table_args__ = (
        UniqueConstraint("shortlist_id", "listing_id", name="uq_shortlist_item"),
    )

    id: int | None = Field(default=None, primary_key=True)
    shortlist_id: int = Field(foreign_key="shortlist.id", index=True)
    listing_id: int = Field(foreign_key="listing.id", index=True)
    note: str | None = None
    added_at: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- #
# CrawlRun — run log, crawl lock, and AI cost ledger
# --------------------------------------------------------------------------- #
class CrawlRun(SQLModel, table=True):
    __tablename__ = "crawl_run"

    id: int | None = Field(default=None, primary_key=True)
    source: str  # display label — set to the search name
    search_id: int | None = Field(default=None, index=True)
    trigger: str = "scheduled"  # scheduled / manual
    status: str = Field(default=RunStatus.RUNNING.value, index=True)
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None

    listings_seen: int = 0
    listings_new: int = 0
    listings_updated: int = 0
    listings_gone: int = 0

    haiku_calls: int = 0
    sonnet_calls: int = 0
    opus_calls: int = 0
    est_cost_usd: float = 0.0

    error: str | None = None
