"""Listing query endpoints: filtered/sorted/paginated list + single fetch."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import asc, desc
from sqlmodel import Session, func, select

from carcatcher.db.engine import get_session
from carcatcher.db.models import (
    Favorite,
    Listing,
    ListingSearch,
    ListingStatus,
    SavedSearch,
)
from carcatcher.normalization.makes import canonical_make
from carcatcher.schemas import filters_from_criteria

router = APIRouter()


def _favorite_ids(session: Session, listing_ids: list[int]) -> set[int]:
    """The subset of `listing_ids` that are favorited (one query, no N+1)."""
    if not listing_ids:
        return set()
    rows = session.exec(
        select(Favorite.listing_id).where(Favorite.listing_id.in_(listing_ids))  # type: ignore[union-attr]
    ).all()
    return set(rows)


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
    battery_kwh: float | None
    battery_soh_pct: int | None
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
    is_favorite: bool = False


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


class FacetCount(BaseModel):
    value: str
    count: int


class BatteryRange(BaseModel):
    min: float
    max: float


class FacetsResponse(BaseModel):
    models: list[FacetCount]
    variants: list[FacetCount]
    battery_kwh: BatteryRange | None


def _build_conditions(
    session: Session,
    *,
    source: str | None,
    search_id: int | None,
    status: str,
    make: str | None,
    model: str | None,
    variant: str | None,
    fuel: str | None,
    transmission: str | None,
    seller_type: str | None,
    year_min: int | None,
    year_max: int | None,
    price_min: int | None,
    price_max: int | None,
    mileage_max: int | None,
    battery_kwh_min: float | None,
    battery_kwh_max: float | None,
    battery_soh_min: int | None,
    deal_score_min: float | None,
    favorites_only: bool = False,
) -> list:
    """Shared WHERE-clause builder for /listings and /listings/facets so both apply
    identical filtering (including the Phase A per-search make/model match)."""
    conditions = []
    if status != "all":
        conditions.append(Listing.status == status)
    if favorites_only:
        conditions.append(Listing.id.in_(select(Favorite.listing_id)))  # type: ignore[union-attr]
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
    if variant:
        conditions.append(func.lower(Listing.variant) == variant.lower())
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
    if battery_kwh_min is not None:
        conditions.append(Listing.battery_kwh >= battery_kwh_min)
    if battery_kwh_max is not None:
        conditions.append(Listing.battery_kwh <= battery_kwh_max)
    if battery_soh_min is not None:
        conditions.append(Listing.battery_soh_pct >= battery_soh_min)
    if deal_score_min is not None:
        conditions.append(Listing.deal_score >= deal_score_min)
    return conditions


@router.get("/listings/facets", response_model=FacetsResponse)
def listing_facets(
    session: Session = Depends(get_session),
    source: str | None = None,
    search_id: int | None = None,
    status: str = ListingStatus.ACTIVE.value,
    make: str | None = None,
    model: str | None = None,
    variant: str | None = None,
    fuel: str | None = None,
    transmission: str | None = None,
    seller_type: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    mileage_max: int | None = None,
    battery_kwh_min: float | None = None,
    battery_kwh_max: float | None = None,
    battery_soh_min: int | None = None,
    deal_score_min: float | None = None,
    favorites_only: bool = False,
) -> FacetsResponse:
    """Distinct models/variants (with counts) and the battery-kWh range present in the
    current result scope, for building refine-by filters on the dashboard."""
    conditions = _build_conditions(
        session,
        source=source, search_id=search_id, status=status, make=make, model=model,
        variant=variant, fuel=fuel, transmission=transmission, seller_type=seller_type,
        year_min=year_min, year_max=year_max, price_min=price_min, price_max=price_max,
        mileage_max=mileage_max, battery_kwh_min=battery_kwh_min,
        battery_kwh_max=battery_kwh_max, battery_soh_min=battery_soh_min,
        deal_score_min=deal_score_min, favorites_only=favorites_only,
    )

    def _counts(column) -> list[FacetCount]:
        rows = session.exec(
            select(column, func.count())
            .where(*conditions, column.is_not(None))
            .group_by(column)
            .order_by(func.count().desc(), column)
        ).all()
        return [FacetCount(value=v, count=c) for v, c in rows]

    lo, hi = session.exec(
        select(func.min(Listing.battery_kwh), func.max(Listing.battery_kwh)).where(
            *conditions, Listing.battery_kwh.is_not(None)
        )
    ).one()
    battery = BatteryRange(min=lo, max=hi) if lo is not None and hi is not None else None

    return FacetsResponse(
        models=_counts(Listing.model),
        variants=_counts(Listing.variant),
        battery_kwh=battery,
    )


@router.get("/listings", response_model=ListingsPage)
def list_listings(
    session: Session = Depends(get_session),
    source: str | None = None,
    search_id: int | None = None,
    status: str = ListingStatus.ACTIVE.value,
    make: str | None = None,
    model: str | None = None,
    variant: str | None = None,
    fuel: str | None = None,
    transmission: str | None = None,
    seller_type: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    mileage_max: int | None = None,
    battery_kwh_min: float | None = None,
    battery_kwh_max: float | None = None,
    battery_soh_min: int | None = None,
    deal_score_min: float | None = None,
    favorites_only: bool = False,
    sort: SortField = "scraped_at",
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(40, ge=1, le=200),
) -> ListingsPage:
    conditions = _build_conditions(
        session,
        source=source, search_id=search_id, status=status, make=make, model=model,
        variant=variant, fuel=fuel, transmission=transmission, seller_type=seller_type,
        year_min=year_min, year_max=year_max, price_min=price_min, price_max=price_max,
        mileage_max=mileage_max, battery_kwh_min=battery_kwh_min,
        battery_kwh_max=battery_kwh_max, battery_soh_min=battery_soh_min,
        deal_score_min=deal_score_min, favorites_only=favorites_only,
    )

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
    fav_ids = _favorite_ids(session, [i.id for i in items])

    def _read(listing: Listing) -> ListingRead:
        out = ListingRead.model_validate(listing)
        out.is_favorite = listing.id in fav_ids
        return out

    return ListingsPage(
        items=[_read(i) for i in items],
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
    out = ListingRead.model_validate(listing)
    out.is_favorite = bool(_favorite_ids(session, [listing.id]))
    return out


@router.put("/listings/{listing_id}/favorite", status_code=204)
def add_favorite(
    listing_id: int, session: Session = Depends(get_session)
) -> Response:
    """Mark a listing as a favorite (idempotent)."""
    if session.get(Listing, listing_id) is None:
        raise HTTPException(status_code=404, detail="listing not found")
    existing = session.exec(
        select(Favorite).where(Favorite.listing_id == listing_id)
    ).first()
    if existing is None:
        session.add(Favorite(listing_id=listing_id))
        session.commit()
    return Response(status_code=204)


@router.delete("/listings/{listing_id}/favorite", status_code=204)
def remove_favorite(
    listing_id: int, session: Session = Depends(get_session)
) -> Response:
    """Unmark a favorite (idempotent — 204 even if it wasn't favorited)."""
    existing = session.exec(
        select(Favorite).where(Favorite.listing_id == listing_id)
    ).first()
    if existing is not None:
        session.delete(existing)
        session.commit()
    return Response(status_code=204)


@router.post("/listings/{listing_id}/evaluate", response_model=ListingRead)
async def evaluate_listing(
    listing_id: int, session: Session = Depends(get_session)
) -> ListingRead:
    """Force a Sonnet evaluation of one listing on demand."""
    from carcatcher.app_state import get_state
    from carcatcher.pipeline.evaluate import evaluate_one
    from carcatcher.settings_store import get_ai_enabled

    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")

    evaluator = get_state().evaluator
    if not evaluator.enabled or not get_ai_enabled(session):
        raise HTTPException(status_code=409, detail="AI is disabled or unconfigured")

    await evaluate_one(session, evaluator, listing)
    session.refresh(listing)
    return ListingRead.model_validate(listing)
