"""Health endpoint. Returns 503 when the database is unreachable so the Proxmox
host watchdog reboots the container (matches the lunch-planner convention)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from carcatcher.db.engine import ping_db

router = APIRouter()


@router.get("/health")
def health() -> JSONResponse:
    if ping_db():
        return JSONResponse(status_code=200, content={"status": "ok"})
    return JSONResponse(status_code=503, content={"status": "db_unavailable"})
