"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from carcatcher.api.routes import (
    health,
    listings,
    models as models_routes,
    recommend,
    refresh,
    saved_searches,
    search,
    settings as settings_routes,
)
from carcatcher.app_state import build_state, get_state, set_state
from carcatcher.config import get_settings
from carcatcher.db.engine import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    state = build_state(settings)
    set_state(state)

    if settings.scheduler_enabled:
        from carcatcher.scheduler.jobs import build_scheduler

        scheduler = build_scheduler()
        scheduler.start()
        state.scheduler = scheduler
        logger.info("scheduler started (cron: %s)", settings.cron_schedule)

    try:
        yield
    finally:
        if state.scheduler is not None:
            state.scheduler.shutdown(wait=False)
        await state.firecrawl.aclose()
        set_state(None)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.include_router(health.router, prefix="/api")
    app.include_router(listings.router, prefix="/api")
    app.include_router(refresh.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(recommend.router, prefix="/api")
    app.include_router(saved_searches.router, prefix="/api")
    app.include_router(settings_routes.router, prefix="/api")
    app.include_router(models_routes.router, prefix="/api")
    return app


app = create_app()
