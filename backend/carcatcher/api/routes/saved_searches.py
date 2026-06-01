"""Saved-search CRUD + on-demand run. Saved searches drive focused crawls and tag
their results; auto_evaluate forces Sonnet evaluation of their matches."""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, desc
from sqlmodel import Session, select

from carcatcher.db.engine import get_engine, get_session
from carcatcher.db.models import (
    Listing,
    ListingSearch,
    SavedSearch,
    ShortlistItem,
    utcnow,
)
from carcatcher.pipeline.run import run_search
from carcatcher.pipeline.snapshot import is_crawl_running
from carcatcher.schemas import StructuredFilters

router = APIRouter()


class SavedSearchCreate(BaseModel):
    name: str
    criteria: StructuredFilters = StructuredFilters()
    nl_query: str | None = None
    auto_evaluate: bool = False
    enabled: bool = True


class SavedSearchUpdate(BaseModel):
    name: str | None = None
    criteria: StructuredFilters | None = None
    nl_query: str | None = None
    auto_evaluate: bool | None = None
    enabled: bool | None = None


class SavedSearchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    criteria: dict
    nl_query: str | None
    auto_evaluate: bool
    enabled: bool
    created_at: datetime
    updated_at: datetime


@router.get("/saved-searches", response_model=list[SavedSearchRead])
def list_saved_searches(session: Session = Depends(get_session)) -> list[SavedSearchRead]:
    rows = session.exec(select(SavedSearch).order_by(desc(SavedSearch.created_at))).all()
    return [SavedSearchRead.model_validate(r) for r in rows]


@router.post("/saved-searches", response_model=SavedSearchRead, status_code=201)
def create_saved_search(
    body: SavedSearchCreate, session: Session = Depends(get_session)
) -> SavedSearchRead:
    ss = SavedSearch(
        name=body.name,
        criteria=body.criteria.model_dump(exclude_none=True),
        nl_query=body.nl_query,
        auto_evaluate=body.auto_evaluate,
        enabled=body.enabled,
    )
    session.add(ss)
    session.commit()
    session.refresh(ss)
    return SavedSearchRead.model_validate(ss)


@router.post(
    "/saved-searches/{search_id}/duplicate",
    response_model=SavedSearchRead,
    status_code=201,
)
def duplicate_saved_search(
    search_id: int, session: Session = Depends(get_session)
) -> SavedSearchRead:
    """Clone a saved search (criteria + nl_query + auto_evaluate) into a new one so the
    user can tweak parameters without rebuilding from scratch."""
    src = session.get(SavedSearch, search_id)
    if src is None:
        raise HTTPException(status_code=404, detail="saved search not found")
    clone = SavedSearch(
        name=f"Copy of {src.name}",
        criteria=dict(src.criteria),
        nl_query=src.nl_query,
        auto_evaluate=src.auto_evaluate,
        enabled=src.enabled,
    )
    session.add(clone)
    session.commit()
    session.refresh(clone)
    return SavedSearchRead.model_validate(clone)


@router.get("/saved-searches/{search_id}", response_model=SavedSearchRead)
def get_saved_search(
    search_id: int, session: Session = Depends(get_session)
) -> SavedSearchRead:
    ss = session.get(SavedSearch, search_id)
    if ss is None:
        raise HTTPException(status_code=404, detail="saved search not found")
    return SavedSearchRead.model_validate(ss)


@router.put("/saved-searches/{search_id}", response_model=SavedSearchRead)
def update_saved_search(
    search_id: int, body: SavedSearchUpdate, session: Session = Depends(get_session)
) -> SavedSearchRead:
    ss = session.get(SavedSearch, search_id)
    if ss is None:
        raise HTTPException(status_code=404, detail="saved search not found")
    if body.name is not None:
        ss.name = body.name
    if body.criteria is not None:
        ss.criteria = body.criteria.model_dump(exclude_none=True)
    if body.nl_query is not None:
        ss.nl_query = body.nl_query
    if body.auto_evaluate is not None:
        ss.auto_evaluate = body.auto_evaluate
    if body.enabled is not None:
        ss.enabled = body.enabled
    ss.updated_at = utcnow()
    session.add(ss)
    session.commit()
    session.refresh(ss)
    return SavedSearchRead.model_validate(ss)


@router.delete("/saved-searches/{search_id}", status_code=204)
def delete_saved_search(search_id: int, session: Session = Depends(get_session)) -> None:
    """Delete a search and its tagged results (orphan listings, unless shortlisted)."""
    ss = session.get(SavedSearch, search_id)
    if ss is None:
        raise HTTPException(status_code=404, detail="saved search not found")

    # Drop this search's links, then delete listings no longer tagged by any search
    # (and not shortlisted).
    session.exec(  # type: ignore[call-overload]
        delete(ListingSearch)
        .where(ListingSearch.search_id == search_id)
        .execution_options(synchronize_session=False)
    )
    session.commit()
    linked = select(ListingSearch.listing_id).distinct()
    shortlisted = select(ShortlistItem.listing_id)
    session.exec(  # type: ignore[call-overload]
        delete(Listing)
        .where(
            Listing.id.not_in(linked),  # type: ignore[union-attr]
            Listing.id.not_in(shortlisted),  # type: ignore[union-attr]
        )
        .execution_options(synchronize_session=False)
    )
    session.delete(ss)
    session.commit()


@router.post("/saved-searches/{search_id}/run")
async def run_saved_search(
    search_id: int,
    session: Session = Depends(get_session),
) -> JSONResponse:
    """Trigger an on-demand crawl of one saved search. No secret required — a manual,
    user-initiated run (the scheduled cron-all path still gates on CRON_SECRET)."""
    if session.get(SavedSearch, search_id) is None:
        raise HTTPException(status_code=404, detail="saved search not found")
    with Session(get_engine()) as s:
        if is_crawl_running(s):
            raise HTTPException(status_code=409, detail="a crawl is already running")

    asyncio.create_task(run_search(search_id, trigger="manual"))
    return JSONResponse(status_code=202, content={"status": "scheduled"})
