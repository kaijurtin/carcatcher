"""Saved-search CRUD. Saved searches drive focused crawls (build_searches) and,
when auto_evaluate is on, force Sonnet evaluation of their matches."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc
from sqlmodel import Session, select

from carcatcher.db.engine import get_session
from carcatcher.db.models import SavedSearch, utcnow
from carcatcher.schemas import StructuredFilters

router = APIRouter()


class SavedSearchCreate(BaseModel):
    name: str
    criteria: StructuredFilters = StructuredFilters()
    nl_query: str | None = None
    auto_evaluate: bool = False


class SavedSearchUpdate(BaseModel):
    name: str | None = None
    criteria: StructuredFilters | None = None
    nl_query: str | None = None
    auto_evaluate: bool | None = None


class SavedSearchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    criteria: dict
    nl_query: str | None
    auto_evaluate: bool
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
    )
    session.add(ss)
    session.commit()
    session.refresh(ss)
    return SavedSearchRead.model_validate(ss)


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
    ss.updated_at = utcnow()
    session.add(ss)
    session.commit()
    session.refresh(ss)
    return SavedSearchRead.model_validate(ss)


@router.delete("/saved-searches/{search_id}", status_code=204)
def delete_saved_search(search_id: int, session: Session = Depends(get_session)) -> None:
    ss = session.get(SavedSearch, search_id)
    if ss is None:
        raise HTTPException(status_code=404, detail="saved search not found")
    session.delete(ss)
    session.commit()
