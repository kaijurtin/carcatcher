"""Manual crawl trigger + recent-run listing."""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc
from sqlmodel import Session, select

from carcatcher.config import get_settings
from carcatcher.db.engine import get_engine, get_session
from carcatcher.db.models import CrawlRun
from carcatcher.pipeline.run import run_all_enabled
from carcatcher.pipeline.snapshot import is_crawl_running

router = APIRouter()


class CrawlRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    listings_seen: int
    listings_new: int
    listings_updated: int
    listings_gone: int
    haiku_calls: int
    sonnet_calls: int
    opus_calls: int
    est_cost_usd: float
    error: str | None


@router.post("/refresh")
async def refresh(x_cron_secret: str | None = Header(default=None)) -> JSONResponse:
    settings = get_settings()
    if not x_cron_secret or not secrets.compare_digest(x_cron_secret, settings.cron_secret):
        raise HTTPException(status_code=401, detail="invalid or missing cron secret")

    with Session(get_engine()) as session:
        if is_crawl_running(session):
            raise HTTPException(status_code=409, detail="a crawl is already running")

    # Fire-and-forget; each search run holds its own lock and records a CrawlRun.
    asyncio.create_task(run_all_enabled(trigger="manual"))
    return JSONResponse(status_code=202, content={"status": "scheduled"})


@router.get("/runs", response_model=list[CrawlRunRead])
def list_runs(
    limit: int = 20, session: Session = Depends(get_session)
) -> list[CrawlRunRead]:
    runs = session.exec(
        select(CrawlRun).order_by(desc(CrawlRun.started_at)).limit(limit)
    ).all()
    return [CrawlRunRead.model_validate(r) for r in runs]
