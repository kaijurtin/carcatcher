"""Tests for GET /api/listings filtering."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from carcatcher.db.models import Listing


def _seed(engine, **overrides) -> int:
    defaults = dict(
        source="vw", source_id="1", url="https://x/1", model="id4", trim="Pro",
        price_eur=30000, mileage_km=10000, year=2024, power_kw=150,
        condition="used", location="Berlin", title="VW ID.4 Pro",
    )
    defaults.update(overrides)
    with Session(engine) as session:
        listing = Listing(**defaults)
        session.add(listing)
        session.commit()
        session.refresh(listing)
        return listing.id


def test_returns_active_listings(client, test_engine):
    _seed(test_engine, source_id="1")
    resp = client.get("/api/listings")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["source_id"] == "1"


def test_filters_by_model(client, test_engine):
    _seed(test_engine, source_id="1", model="id3")
    _seed(test_engine, source_id="2", model="id4")
    resp = client.get("/api/listings", params={"model": "id4"})
    assert [i["source_id"] for i in resp.json()] == ["2"]


def test_filters_by_source(client, test_engine):
    _seed(test_engine, source_id="1", source="vw")
    _seed(test_engine, source_id="2", source="autoscout24")
    resp = client.get("/api/listings", params={"source": "autoscout24"})
    assert [i["source_id"] for i in resp.json()] == ["2"]


def test_filters_by_max_price(client, test_engine):
    _seed(test_engine, source_id="1", price_eur=20000)
    _seed(test_engine, source_id="2", price_eur=40000)
    resp = client.get("/api/listings", params={"max_price": 30000})
    assert [i["source_id"] for i in resp.json()] == ["1"]


def test_filters_by_max_km(client, test_engine):
    _seed(test_engine, source_id="1", mileage_km=5000)
    _seed(test_engine, source_id="2", mileage_km=50000)
    resp = client.get("/api/listings", params={"max_km": 10000})
    assert [i["source_id"] for i in resp.json()] == ["1"]


def test_filters_by_trim_substring_case_insensitive(client, test_engine):
    _seed(test_engine, source_id="1", trim="Pro Performance")
    _seed(test_engine, source_id="2", trim="Pure")
    resp = client.get("/api/listings", params={"trim": "pro"})
    assert [i["source_id"] for i in resp.json()] == ["1"]


def test_excludes_gone_listings_by_default(client, test_engine):
    _seed(test_engine, source_id="1", status="gone")
    resp = client.get("/api/listings")
    assert resp.json() == []


def test_sorted_by_price_ascending_with_nulls_last(client, test_engine):
    _seed(test_engine, source_id="1", price_eur=40000)
    _seed(test_engine, source_id="2", price_eur=20000)
    _seed(test_engine, source_id="3", price_eur=None)
    resp = client.get("/api/listings")
    assert [i["source_id"] for i in resp.json()] == ["2", "1", "3"]


def test_listing_tag_defaults_to_null(client, test_engine):
    _seed(test_engine, source_id="1")
    resp = client.get("/api/listings")
    assert resp.json()[0]["tag"] is None


def test_patch_tag_sets_and_returns_the_updated_listing(client, test_engine):
    listing_id = _seed(test_engine, source_id="1")
    resp = client.patch(f"/api/listings/{listing_id}/tag", json={"tag": "star"})
    assert resp.status_code == 200
    assert resp.json()["tag"] == "star"

    resp = client.get("/api/listings")
    assert resp.json()[0]["tag"] == "star"


def test_patch_tag_null_clears_it(client, test_engine):
    listing_id = _seed(test_engine, source_id="1", tag="7")
    resp = client.patch(f"/api/listings/{listing_id}/tag", json={"tag": None})
    assert resp.status_code == 200
    assert resp.json()["tag"] is None


def test_patch_tag_rejects_an_invalid_value(client, test_engine):
    listing_id = _seed(test_engine, source_id="1")
    resp = client.patch(f"/api/listings/{listing_id}/tag", json={"tag": "banana"})
    assert resp.status_code == 422


def test_patch_tag_404_for_a_missing_listing(client, test_engine):
    resp = client.patch("/api/listings/999/tag", json={"tag": "star"})
    assert resp.status_code == 404


def test_patch_tag_accepts_every_allowed_value(client, test_engine):
    listing_id = _seed(test_engine, source_id="1")
    for value in ["star", "plus", "minus", *[str(n) for n in range(1, 11)]]:
        resp = client.patch(f"/api/listings/{listing_id}/tag", json={"tag": value})
        assert resp.status_code == 200, value
        assert resp.json()["tag"] == value


def test_battery_kwh_included_in_response(client, test_engine):
    _seed(test_engine, source_id="1", battery_kwh=82.0)
    resp = client.get("/api/listings")
    assert resp.json()[0]["battery_kwh"] == 82.0


def test_battery_kwh_defaults_to_null(client, test_engine):
    _seed(test_engine, source_id="1")
    resp = client.get("/api/listings")
    assert resp.json()[0]["battery_kwh"] is None


def test_distance_km_is_null_without_coordinates(client, test_engine):
    _seed(test_engine, source_id="1")
    resp = client.get("/api/listings")
    assert resp.json()[0]["distance_km"] is None


def test_distance_km_is_zero_at_the_home_point(client, test_engine):
    from carcatcher.config import get_settings

    settings = get_settings()
    _seed(
        test_engine, source_id="1",
        latitude=settings.home_latitude, longitude=settings.home_longitude,
    )
    resp = client.get("/api/listings")
    assert resp.json()[0]["distance_km"] == 0.0


def test_distance_km_computed_from_coordinates(client, test_engine):
    # Berlin, ~584 km from the fixed home point (66663 Merzig) — sanity-checks
    # that a real, non-zero coordinate pair produces a plausible distance.
    _seed(test_engine, source_id="1", latitude=52.5200, longitude=13.4050)
    resp = client.get("/api/listings")
    assert resp.json()[0]["distance_km"] == pytest.approx(584.4, abs=1.0)
