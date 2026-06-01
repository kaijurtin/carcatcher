"""DB-level tests: battery filters in search_listings + battery fields in API responses."""

from __future__ import annotations

from sqlmodel import Session

from carcatcher.db.engine import get_engine
from carcatcher.db.models import Listing
from carcatcher.queries import search_listings
from carcatcher.schemas import StructuredFilters


def _seed_evs(session: Session) -> None:
    session.add_all(
        [
            Listing(
                source="autoscout24", source_id="e1", url="e1",
                raw_title="VW ID.4 Pure", make="Volkswagen", model="ID.4",
                variant="Pure", fuel="electric", battery_kwh=52.0, battery_soh_pct=95,
            ),
            Listing(
                source="autoscout24", source_id="e2", url="e2",
                raw_title="VW ID.4 Pro", make="Volkswagen", model="ID.4",
                variant="Pro", fuel="electric", battery_kwh=77.0, battery_soh_pct=88,
            ),
            Listing(
                source="autoscout24", source_id="e3", url="e3",
                raw_title="VW Golf", make="Volkswagen", model="Golf",
                fuel="petrol", battery_kwh=None, battery_soh_pct=None,
            ),
        ]
    )
    session.commit()


def test_battery_kwh_min_filters_small_packs(test_engine):
    with Session(get_engine()) as s:
        _seed_evs(s)
        rows = search_listings(s, StructuredFilters(battery_kwh_min=70))
    assert {r.source_id for r in rows} == {"e2"}


def test_battery_kwh_max_filters_large_packs(test_engine):
    with Session(get_engine()) as s:
        _seed_evs(s)
        rows = search_listings(s, StructuredFilters(battery_kwh_max=60))
    assert {r.source_id for r in rows} == {"e1"}


def test_battery_soh_min_floor(test_engine):
    with Session(get_engine()) as s:
        _seed_evs(s)
        rows = search_listings(s, StructuredFilters(battery_soh_min=90))
    assert {r.source_id for r in rows} == {"e1"}


def test_listing_read_exposes_battery_fields(client):
    with Session(get_engine()) as s:
        _seed_evs(s)
    body = client.get("/api/listings").json()
    by_id = {i["source_id"]: i for i in body["items"]}
    assert by_id["e2"]["battery_kwh"] == 77.0
    assert by_id["e2"]["battery_soh_pct"] == 88
    assert by_id["e3"]["battery_kwh"] is None


def test_listings_filter_by_variant_and_battery(client):
    with Session(get_engine()) as s:
        _seed_evs(s)
    # variant filter is case-insensitive exact match
    r = client.get("/api/listings", params={"variant": "pro"})
    assert {i["source_id"] for i in r.json()["items"]} == {"e2"}
    # battery kWh min
    r = client.get("/api/listings", params={"battery_kwh_min": 70})
    assert {i["source_id"] for i in r.json()["items"]} == {"e2"}


def test_facets_returns_models_variants_and_battery_range(client):
    with Session(get_engine()) as s:
        _seed_evs(s)
    facets = client.get("/api/listings/facets").json()
    models = {m["value"]: m["count"] for m in facets["models"]}
    assert models == {"ID.4": 2, "Golf": 1}
    variants = {v["value"] for v in facets["variants"]}
    assert variants == {"Pure", "Pro"}  # Golf has no variant -> excluded
    assert facets["battery_kwh"] == {"min": 52.0, "max": 77.0}


def test_facets_cascade_with_model_filter(client):
    with Session(get_engine()) as s:
        _seed_evs(s)
    facets = client.get("/api/listings/facets", params={"model": "ID.4"}).json()
    assert {v["value"] for v in facets["variants"]} == {"Pure", "Pro"}
    assert facets["battery_kwh"] == {"min": 52.0, "max": 77.0}


def test_facets_empty_battery_range_is_null(client):
    with Session(get_engine()) as s:
        s.add(
            Listing(
                source="kleinanzeigen", source_id="p1", url="p1",
                raw_title="VW Golf", make="Volkswagen", model="Golf", fuel="petrol",
            )
        )
        s.commit()
    facets = client.get("/api/listings/facets").json()
    assert facets["battery_kwh"] is None
