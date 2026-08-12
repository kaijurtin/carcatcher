"""Manual crawl trigger — synchronous (2 sources x 2 models, no AI calls, fast
enough to complete within one request)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import Session

from carcatcher.app_state import get_state
from carcatcher.crawl import run_crawl
from carcatcher.db.engine import get_engine

router = APIRouter()


class RefreshSummary(BaseModel):
    added: int
    updated: int
    gone: int
    failed_sources: list[str]
    refreshed_at: datetime


@router.post("/refresh", response_model=RefreshSummary)
def refresh() -> RefreshSummary:
    state = get_state()
    with Session(get_engine()) as session:
        summary = run_crawl(session, state.parsers, state.geocoder)
    return RefreshSummary(
        added=summary.added,
        updated=summary.updated,
        gone=summary.gone,
        failed_sources=summary.failed_sources,
        refreshed_at=summary.refreshed_at,
    )
