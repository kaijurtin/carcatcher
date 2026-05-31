"""Reusable listing queries (shared by NL search and could back /api/listings)."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import asc, desc
from sqlmodel import Session, select

from carcatcher.db.models import Listing, ListingSearch, ListingStatus
from carcatcher.schemas import StructuredFilters

_SORT_COLUMNS = {
    "deal_score": Listing.deal_score,
    "price": Listing.price,
    "year": Listing.year,
    "mileage_km": Listing.mileage_km,
    "scraped_at": Listing.scraped_at,
}


def search_listings(
    session: Session,
    filters: StructuredFilters,
    *,
    sort: str = "deal_score",
    order: Literal["asc", "desc"] = "desc",
    limit: int = 50,
    search_id: int | None = None,
) -> list[Listing]:
    """Active listings matching the structured filters, sorted (NULLs last).
    If `search_id` is given, restrict to listings tagged active for that search."""
    conditions = [Listing.status == ListingStatus.ACTIVE.value]
    if search_id is not None:
        active_for_search = select(ListingSearch.listing_id).where(
            ListingSearch.search_id == search_id,
            ListingSearch.status == ListingStatus.ACTIVE.value,
        )
        conditions.append(Listing.id.in_(active_for_search))  # type: ignore[union-attr]
    if filters.make:
        conditions.append(Listing.make.ilike(filters.make))  # type: ignore[union-attr]
    if filters.model:
        conditions.append(Listing.model.ilike(filters.model))  # type: ignore[union-attr]
    if filters.fuel:
        conditions.append(Listing.fuel == filters.fuel)
    if filters.transmission:
        conditions.append(Listing.transmission == filters.transmission)
    if filters.seller_type:
        conditions.append(Listing.seller_type == filters.seller_type)
    if filters.year_min is not None:
        conditions.append(Listing.year >= filters.year_min)
    if filters.year_max is not None:
        conditions.append(Listing.year <= filters.year_max)
    if filters.price_min is not None:
        conditions.append(Listing.price >= filters.price_min)
    if filters.price_max is not None:
        conditions.append(Listing.price <= filters.price_max)
    if filters.mileage_max is not None:
        conditions.append(Listing.mileage_km <= filters.mileage_max)
    if filters.plz:
        conditions.append(Listing.location_plz == filters.plz)

    col = _SORT_COLUMNS.get(sort, Listing.deal_score)
    direction = desc if order == "desc" else asc
    stmt = (
        select(Listing)
        .where(*conditions)
        .order_by(col.is_(None), direction(col), desc(Listing.id))
        .limit(limit)
    )
    return list(session.exec(stmt).all())
