"""Shared domain/API schemas (pydantic) used across scraping, scoring, AI and API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StructuredFilters(BaseModel):
    """A normalized car search. Drives both scraping (search URL building) and the
    DB query for `/api/listings`. Produced by the user (saved search) or by the AI
    natural-language translator. All fields optional — absent = no constraint."""

    make: str | None = None
    model: str | None = None
    variant: str | None = None
    year_min: int | None = None
    year_max: int | None = None
    price_min: int | None = None
    price_max: int | None = None
    mileage_max: int | None = None
    fuel: str | None = None
    transmission: str | None = None
    seller_type: str | None = None
    plz: str | None = None
    radius_km: int | None = None
    keywords: str | None = Field(default=None, description="Free-text fallback query")


def filters_from_criteria(criteria: dict) -> StructuredFilters:
    """Build StructuredFilters from a stored `SavedSearch.criteria` dict, ignoring
    any keys that aren't filter fields."""
    fields = StructuredFilters.model_fields
    return StructuredFilters(**{k: v for k, v in criteria.items() if k in fields})
