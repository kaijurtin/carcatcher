"""Listing query endpoint: filtered list of active (or all) listings."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import asc
from sqlmodel import Session, func, select

from carcatcher.db.engine import get_session
from carcatcher.db.models import Listing, ListingStatus

router = APIRouter()


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
    condition: str
    location: str | None
    title: str
    status: str
    first_seen_at: datetime
    last_seen_at: datetime


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
    return [ListingRead.model_validate(i) for i in items]
