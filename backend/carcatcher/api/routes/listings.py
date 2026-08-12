"""Listing query endpoint: filtered list of active (or all) listings."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import asc
from sqlmodel import Session, func, select

from carcatcher.config import get_settings
from carcatcher.db.engine import get_session
from carcatcher.db.models import Listing, ListingStatus
from carcatcher.geocoding import haversine_km

router = APIRouter()

TagValue = Literal[
    "star", "plus", "minus", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"
]


class ListingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    source_id: str
    url: str
    model: str
    trim: str
    price_eur: int | None
    mileage_km: int | None
    year: int | None
    power_kw: int | None
    battery_kwh: float | None
    condition: str
    location: str | None
    title: str
    tag: str | None
    status: str
    first_seen_at: datetime
    last_seen_at: datetime
    distance_km: float | None = None


class TagUpdate(BaseModel):
    tag: TagValue | None


def _to_read(listing: Listing) -> ListingRead:
    """Build the API representation of `listing`, computing `distance_km` from
    its coordinates against the fixed home point — never stored, always
    derived, so it can't go stale if the home point ever changes."""
    read = ListingRead.model_validate(listing)
    if listing.latitude is not None and listing.longitude is not None:
        settings = get_settings()
        read.distance_km = round(
            haversine_km(
                listing.latitude, listing.longitude, settings.home_latitude, settings.home_longitude
            ),
            1,
        )
    return read


@router.get("/listings", response_model=list[ListingRead])
def list_listings(
    session: Session = Depends(get_session),
    model: Literal["id3", "id4"] | None = None,
    source: str | None = None,
    max_price: int | None = None,
    max_km: int | None = None,
    trim: str | None = None,
    status: str = ListingStatus.ACTIVE.value,
) -> list[ListingRead]:
    conditions = []
    if status != "all":
        conditions.append(Listing.status == status)
    if model:
        conditions.append(Listing.model == model)
    if source:
        conditions.append(Listing.source == source)
    if max_price is not None:
        conditions.append(Listing.price_eur <= max_price)
    if max_km is not None:
        conditions.append(Listing.mileage_km <= max_km)
    if trim:
        conditions.append(func.lower(Listing.trim).like(f"%{trim.lower()}%"))
    stmt = (
        select(Listing)
        .where(*conditions)
        .order_by(Listing.price_eur.is_(None), asc(Listing.price_eur), Listing.id)
    )
    items = session.exec(stmt).all()
    return [_to_read(i) for i in items]


@router.patch("/listings/{listing_id}/tag", response_model=ListingRead)
def set_listing_tag(
    listing_id: int, payload: TagUpdate, session: Session = Depends(get_session)
) -> ListingRead:
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="listing not found")
    listing.tag = payload.tag
    session.add(listing)
    session.commit()
    session.refresh(listing)
    return _to_read(listing)
