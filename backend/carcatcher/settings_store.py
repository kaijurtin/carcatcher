"""Runtime settings backed by the single-row `AppSetting` table.

The dashboard AI toggle lives here so it survives restarts and is the single source
of truth at run time. The env `ai_disabled` flag (config.Settings) is a hard
kill-switch: when set, AI is off regardless of the DB row.
"""

from __future__ import annotations

from sqlmodel import Session

from carcatcher.config import get_settings
from carcatcher.db.models import AppSetting, utcnow

_ROW_ID = 1


def _get_or_create(session: Session) -> AppSetting:
    row = session.get(AppSetting, _ROW_ID)
    if row is None:
        row = AppSetting(id=_ROW_ID)
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def get_ai_enabled(session: Session) -> bool:
    """Effective AI on/off: env hard-off wins, else the DB row, default True."""
    if get_settings().ai_disabled:
        return False
    row = session.get(AppSetting, _ROW_ID)
    return True if row is None else row.ai_enabled


def set_ai_enabled(session: Session, value: bool) -> AppSetting:
    """Persist the runtime AI toggle. Returns the updated row."""
    row = _get_or_create(session)
    row.ai_enabled = value
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
