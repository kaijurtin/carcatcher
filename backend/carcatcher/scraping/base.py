"""Parser interface: turn a model search into unified RawListing rows."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

Model = Literal["id3", "id4"]


@dataclass
class RawListing:
    """One listing, already in the shape `crawl.py` upserts into `Listing`."""

    source: str
    source_id: str
    url: str
    model: Model
    trim: str
    price_eur: int | None
    mileage_km: int | None
    year: int | None
    power_kw: int | None
    condition: str  # "new" | "used"
    location: str | None
    title: str


class Parser(ABC):
    """One source (autoscout24, vw, …)."""

    name: str

    @abstractmethod
    def fetch_listings(self, model: Model) -> list[RawListing]:
        """Fetch and parse every listing for `model` from this source."""
        ...


# ============================================================================
# BACKWARDS COMPATIBILITY (for existing code using old interfaces)
# These will be removed in Task 3/5 when old scrapers and pipeline are updated
# ============================================================================


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


@dataclass
class ListingStub:
    """DEPRECATED: old list-page representation. Use RawListing instead."""

    source: str
    source_id: str
    url: str
    title: str
    price_hint: str | None = None
    location_hint: str | None = None
    image_hint: str | None = None
    tags: list[str] = field(default_factory=list)
    description_hint: str | None = None


@dataclass
class RawPage:
    """DEPRECATED: old detail-page representation."""

    url: str
    markdown: str
    html: str | None = None
    images: list[str] = field(default_factory=list)
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = sha256_text(self.markdown or self.html or "")


class Scraper(ABC):
    """DEPRECATED: old scraper base. Use Parser instead."""

    name: str
    base_url: str
    provides_structured_data: bool = False

    @abstractmethod
    async def search(self, filters: object, *, max_pages: int) -> AsyncIterator:
        """Yield listing stubs across up to `max_pages` results pages."""
        raise NotImplementedError
        yield  # pragma: no cover  (makes this an async generator)

    @abstractmethod
    async def fetch_detail(self, url: str) -> RawPage:
        """Fetch + render one detail page."""
        ...

    @abstractmethod
    def parse_source_id(self, url: str) -> str:
        """Extract the stable source-local id from a detail URL."""
        ...
