"""Tests for GET /api/listings filtering."""

from __future__ import annotations

from sqlmodel import Session

from carcatcher.db.models import Listing


def _seed(engine, **overrides):
    defaults = dict(
        source="vw", source_id="1", url="https://x/1", model="id4", trim="Pro",
        price_eur=30000, mileage_km=10000, year=2024, power_kw=150,
        condition="used", location="Berlin", title="VW ID.4 Pro",
    )
    defaults.update(overrides)
    with Session(engine) as session:
        session.add(Listing(**defaults))
        session.commit()


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
