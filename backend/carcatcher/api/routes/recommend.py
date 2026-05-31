"""Opus cross-candidate recommendation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from carcatcher.api.routes.listings import ListingRead
from carcatcher.db.engine import get_session
from carcatcher.db.models import Listing

router = APIRouter()


class RecommendRequest(BaseModel):
    listing_ids: list[int]


class RankedPick(BaseModel):
    listing_id: int
    rank: int
    reason: str


class Recommendation(BaseModel):
    top_pick_id: int
    summary: str
    ranking: list[RankedPick]
    caveats: list[str] = []


class RecommendResponse(BaseModel):
    recommendation: Recommendation
    listings: list[ListingRead]


@router.post("/recommend", response_model=RecommendResponse)
async def recommend(
    req: RecommendRequest, session: Session = Depends(get_session)
) -> RecommendResponse:
    from carcatcher.app_state import get_state

    if len(req.listing_ids) < 2:
        raise HTTPException(status_code=400, detail="select at least 2 listings")
    if len(req.listing_ids) > 8:
        raise HTTPException(status_code=400, detail="select at most 8 listings")

    recommender = get_state().recommender
    if not recommender.enabled:
        raise HTTPException(status_code=409, detail="AI is disabled or unconfigured")

    listings = [
        li for li in (session.get(Listing, i) for i in req.listing_ids) if li is not None
    ]
    if len(listings) < 2:
        raise HTTPException(status_code=404, detail="not enough listings found")

    data, _ = await recommender.recommend(listings)
    return RecommendResponse(
        recommendation=Recommendation(
            top_pick_id=data["top_pick_id"],
            summary=data.get("summary", ""),
            ranking=[RankedPick(**r) for r in data.get("ranking", [])],
            caveats=data.get("caveats", []) or [],
        ),
        listings=[ListingRead.model_validate(li) for li in listings],
    )
