"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from carcatcher.api.routes import health
from carcatcher.config import get_settings
from carcatcher.db.engine import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables exist. (Scheduler is wired in P3.)
    init_db()
    yield
    # Shutdown: nothing yet.


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.include_router(health.router, prefix="/api")
    return app


app = create_app()
