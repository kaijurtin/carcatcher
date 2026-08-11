"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from carcatcher.api.routes import health, listings, refresh
from carcatcher.app_state import build_state, set_state
from carcatcher.config import get_settings
from carcatcher.db.engine import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    set_state(build_state())
    try:
        yield
    finally:
        set_state(None)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
    app.include_router(health.router, prefix="/api")
    app.include_router(listings.router, prefix="/api")
    app.include_router(refresh.router, prefix="/api")
    return app


app = create_app()
