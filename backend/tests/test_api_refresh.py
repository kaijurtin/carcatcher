"""Tests for POST /api/refresh."""

from __future__ import annotations

from carcatcher.app_state import AppState, set_state
from carcatcher.scraping.base import RawListing


class _FakeParser:
    def __init__(self, name, listings):
        self.name = name
        self._listings = listings

    def fetch_listings(self, model):
        return [l for l in self._listings if l.model == model]


def _raw(source_id):
    return RawListing(
        source="vw", source_id=source_id, url=f"https://x/{source_id}", model="id4",
        trim="Pro", price_eur=30000, mileage_km=1000, year=2024, power_kw=150,
        battery_kwh=None, condition="used", location="Berlin", title="VW ID.4 Pro",
    )


def test_refresh_returns_summary(client, test_engine):
    set_state(AppState(parsers={"vw": _FakeParser("vw", [_raw("1")])}))
    resp = client.post("/api/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == 1
    assert body["updated"] == 0
    assert body["gone"] == 0
    assert body["failed_sources"] == []
    assert "refreshed_at" in body


def test_refresh_then_listings_reflects_new_rows(client, test_engine):
    set_state(AppState(parsers={"vw": _FakeParser("vw", [_raw("1")])}))
    client.post("/api/refresh")
    resp = client.get("/api/listings")
    assert len(resp.json()) == 1
