"""Pluggable scraper interface.

A `Scraper` turns a `StructuredFilters` into a stream of cheap `ListingStub`s
(one network fetch per results page) and can fetch a full `RawPage` for any
detail URL. Sites are added by implementing this ABC + registering in registry.py.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from carcatcher.schemas import StructuredFilters


@dataclass
class ListingStub:
    """The cheap, list-page representation of a listing — enough to dedup and
    decide whether a (costly) detail fetch is warranted."""

    source: str
    source_id: str
    url: str
    title: str
    price_hint: str | None = None
    location_hint: str | None = None
    image_hint: str | None = None
    # Lightweight specs sometimes present on the card (km, year, etc.).
    tags: list[str] = field(default_factory=list)
    description_hint: str | None = None


@dataclass
class RawPage:
    """A fetched + rendered detail page. `markdown` is the Haiku input (P2)."""

    url: str
    markdown: str
    html: str | None = None
    images: list[str] = field(default_factory=list)
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = sha256_text(self.markdown or self.html or "")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


class Scraper(ABC):
    """Abstract base for a single source (kleinanzeigen, autoscout24, …)."""

    name: str
    base_url: str

    @abstractmethod
    async def search(
        self, filters: StructuredFilters, *, max_pages: int
    ) -> AsyncIterator[ListingStub]:
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

    def basic_specs(self, stub: ListingStub) -> dict:
        """Deterministic specs cheaply available on the list card (price, mileage,
        year, negotiable). Source-specific; default none. Haiku fills the rest (P2)."""
        return {}
