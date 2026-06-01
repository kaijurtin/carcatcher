"""Runtime settings endpoints — currently the dashboard AI on/off toggle."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from carcatcher.db.engine import get_session
from carcatcher.settings_store import get_ai_enabled, set_ai_enabled

router = APIRouter()


class SettingsRead(BaseModel):
    ai_enabled: bool  # effective on/off (env kill-switch applied)
    ai_configured: bool  # whether an Anthropic key is present at all


class AiToggleUpdate(BaseModel):
    enabled: bool


def _ai_configured() -> bool:
    """True if AI is actually wired (key present), ignoring the runtime toggle, so
    the UI can distinguish 'key missing' from 'toggled off'."""
    from carcatcher.app_state import get_state

    try:
        return get_state().extractor.enabled
    except RuntimeError:
        return False


@router.get("/settings", response_model=SettingsRead)
def read_settings(session: Session = Depends(get_session)) -> SettingsRead:
    return SettingsRead(
        ai_enabled=get_ai_enabled(session),
        ai_configured=_ai_configured(),
    )


@router.put("/settings/ai", response_model=SettingsRead)
def update_ai(
    body: AiToggleUpdate, session: Session = Depends(get_session)
) -> SettingsRead:
    set_ai_enabled(session, body.enabled)
    return SettingsRead(
        ai_enabled=get_ai_enabled(session),
        ai_configured=_ai_configured(),
    )
