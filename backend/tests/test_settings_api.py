"""Settings API + runtime AI toggle behaviour."""

from __future__ import annotations

from sqlmodel import Session

from carcatcher import config
from carcatcher.config import Settings
from carcatcher.db.engine import get_engine
from carcatcher.db.models import AppSetting
from carcatcher.settings_store import get_ai_enabled, set_ai_enabled


def test_get_settings_defaults_to_ai_enabled(client):
    # conftest sets ai_disabled=True (env kill-switch) -> effective off, not configured.
    body = client.get("/api/settings").json()
    assert body["ai_enabled"] is False
    assert body["ai_configured"] is False


def test_put_ai_toggle_persists(client):
    client.put("/api/settings/ai", json={"enabled": False})
    with Session(get_engine()) as s:
        row = s.get(AppSetting, 1)
        assert row is not None and row.ai_enabled is False
    client.put("/api/settings/ai", json={"enabled": True})
    with Session(get_engine()) as s:
        assert s.get(AppSetting, 1).ai_enabled is True


def test_env_kill_switch_overrides_db_row(test_engine):
    # DB row says enabled, but env ai_disabled forces effective-off.
    with Session(get_engine()) as s:
        set_ai_enabled(s, True)
        assert get_ai_enabled(s) is False  # conftest ai_disabled=True wins


def test_runtime_toggle_respected_when_ai_configured(test_engine):
    # Flip env kill-switch off so the DB row is authoritative.
    config._settings = Settings(
        scheduler_enabled=False, ai_disabled=False, scrape_min_interval_ms=0,
    )
    try:
        with Session(get_engine()) as s:
            assert get_ai_enabled(s) is True  # no row -> default True
            set_ai_enabled(s, False)
            assert get_ai_enabled(s) is False
    finally:
        config._settings = None
