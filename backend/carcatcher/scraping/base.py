"""Parser interface: turn a model search into unified RawListing rows."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
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
    battery_kwh: float | None
    condition: str  # "new" | "used"
    location: str | None
    title: str


@dataclass
class FetchResult:
    """One parser's fetch for one model: its listings, and whether the fetch
    reliably covered everything currently live for this model. `complete` is
    False whenever a source-specific limit (e.g. a page cap) may have left
    real listings unseen — crawl.py must not mark a source's un-seen
    listings `gone` off the back of an incomplete fetch."""

    listings: list[RawListing]
    complete: bool


class Parser(ABC):
    """One source (autoscout24, vw, …)."""

    name: str

    @abstractmethod
    def fetch_listings(self, model: Model) -> FetchResult:
        """Fetch and parse every listing for `model` from this source."""
        ...
