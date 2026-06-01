"""Listing query endpoints: filtered/sorted/paginated list + single fetch."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import asc, desc
from sqlmodel import Session, func, select

from carcatcher.db.engine import get_session
from carcatcher.db.models import Listing, ListingSearch, ListingStatus, SavedSearch
from carcatcher.normalization.makes import canonical_make
from carcatcher.schemas import filters_from_criteria

router = APIRouter()


class ListingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    source_id: str
    url: str
    status: str
    raw_title: str
    raw_price: str | None
    location_raw: str | None
    images: list[str]
    price: int | None
    price_negotiable: bool
    mileage_km: int | None
    year: int | None
    make: str | None
    model: str | None
    variant: str | None
    fuel: str | None
    transmission: str | None
    power_kw: int | None
    body_type: str | None
    location_city: str | None
    location_plz: str | None
    seller_type: str | None
    fair_price_estimate: int | None
    deal_score: float | None
    comp_count: int | None
    ai_evaluation: dict | None
    ai_evaluated_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    scraped_at: datetime


class ListingsPage(BaseModel):
    items: list[ListingRead]
    total: int
    page: int
    page_size: int


SortField = Literal["scraped_at", "price", "deal_score", "year", "mileage_km"]

_SORT_COLUMNS = {
    "scraped_at": Listing.scraped_at,
    "price": Listing.price,
    "deal_score": Listing.deal_score,
    "year": Listing.year,
    "mileage_km": Listing.mileage_km,
}


@router.get("/listings", response_model=ListingsPage)
def list_listings(
    session: Session = Depends(get_session),
    source: str | None = None,
    search_id: int | None = None,
    status: str = ListingStatus.ACTIVE.value,
    make: str | None = None,
    model: str | None = None,
    fuel: str | None = None,
    transmission: str | None = None,
    seller_type: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    mileage_max: int | None = None,
    deal_score_min: float | None = None,
    sort: SortField = "scraped_at",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(40, ge=1, le=200),
) -> ListingsPage:
    conditions = []
    if status != "all":
        conditions.append(Listing.status == status)
    if search_id is not None:
        active_for_search = select(ListingSearch.listing_id).where(
            ListingSearch.search_id == search_id,
            ListingSearch.status == ListingStatus.ACTIVE.value,
        )
        conditions.append(Listing.id.in_(active_for_search))  # type: ignore[union-attr]
        # Crawl tagging is unconditional, so source "related ads" with a different
        # make/model get tagged too. Only show listings that actually match the
        # saved search's own make/model criteria (make canonicalized: VW->Volkswagen).
        saved = session.get(SavedSearch, search_id)
        if saved is not None:
            criteria = filters_from_criteria(saved.criteria)
            if criteria.make:
                conditions.append(
                    func.lower(Listing.make) == canonical_make(criteria.make).lower()
                )
            if criteria.model:
                conditions.append(func.lower(Listing.model) == criteria.model.lower())
    if source:
        conditions.append(Listing.source == source)
    if make:
        conditions.append(Listing.make == make)
    if model:
        conditions.append(Listing.model == model)
    if fuel:
        conditions.append(Listing.fuel == fuel)
    if transmission:
        conditions.append(Listing.transmission == transmission)
    if seller_type:
        conditions.append(Listing.seller_type == seller_type)
    if year_min is not None:
        conditions.append(Listing.year >= year_min)
    if year_max is not None:
        conditions.append(Listing.year <= year_max)
    if price_min is not None:
        conditions.append(Listing.price >= price_min)
    if price_max is not None:
        conditions.append(Listing.price <= price_max)
    if mileage_max is not None:
        conditions.append(Listing.mileage_km <= mileage_max)
    if deal_score_min is not None:
        conditions.append(Listing.deal_score >= deal_score_min)

    total = session.exec(
        select(func.count()).select_from(Listing).where(*conditions)
    ).one()

    col = _SORT_COLUMNS[sort]
    direction = desc if order == "desc" else asc
    # NULLs sort last regardless of direction (cleaner for price/deal_score).
    stmt = (
        select(Listing)
        .where(*conditions)
        .order_by(col.is_(None), direction(col), desc(Listing.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = session.exec(stmt).all()

    return ListingsPage(
        items=[ListingRead.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/listings/{listing_id}", response_model=ListingRead)
def get_listing(
    listing_id: int, session: Session = Depends(get_session)
) -> ListingRead:
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")
    return ListingRead.model_validate(listing)


@router.post("/listings/{listing_id}/evaluate", response_model=ListingRead)
async def evaluate_listing(
    listing_id: int, session: Session = Depends(get_session)
) -> ListingRead:
    """Force a Sonnet evaluation of one listing on demand."""
    from carcatcher.app_state import get_state
    from carcatcher.pipeline.evaluate import evaluate_one

    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")

    evaluator = get_state().evaluator
    if not evaluator.enabled:
        raise HTTPException(status_code=409, detail="AI is disabled or unconfigured")

    await evaluate_one(session, evaluator, listing)
    session.refresh(listing)
    return ListingRead.model_validate(listing)
