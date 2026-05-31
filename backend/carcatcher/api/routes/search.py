"""Natural-language search endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from carcatcher.api.routes.listings import ListingRead
from carcatcher.db.engine import get_session
from carcatcher.queries import search_listings
from carcatcher.schemas import StructuredFilters

router = APIRouter()


class NlSearchRequest(BaseModel):
    query: str
    limit: int = 50


class RankingEntry(BaseModel):
    field: str
    direction: str


class NlSearchResponse(BaseModel):
    query: str
    filters: StructuredFilters
    ranking: list[RankingEntry]
    rationale: str
    results: list[ListingRead]
    total: int


@router.post("/search/nl", response_model=NlSearchResponse)
async def nl_search(
    req: NlSearchRequest, session: Session = Depends(get_session)
) -> NlSearchResponse:
    from carcatcher.app_state import get_state

    translator = get_state().translator
    if not translator.enabled:
        raise HTTPException(status_code=409, detail="AI is disabled or unconfigured")

    data, _ = await translator.translate(req.query)
    raw_filters = data.get("filters", {}) or {}
    filters = StructuredFilters(
        **{k: v for k, v in raw_filters.items() if k in StructuredFilters.model_fields}
    )
    ranking = [
        RankingEntry(field=r["field"], direction=r.get("direction", "desc"))
        for r in (data.get("ranking") or [])
        if r.get("field")
    ]
    sort = ranking[0].field if ranking else "deal_score"
    order = ranking[0].direction if ranking else "desc"

    listings = search_listings(
        session, filters, sort=sort, order=order, limit=req.limit
    )
    return NlSearchResponse(
        query=req.query,
        filters=filters,
        ranking=ranking,
        rationale=data.get("rationale", ""),
        results=[ListingRead.model_validate(li) for li in listings],
        total=len(listings),
    )
