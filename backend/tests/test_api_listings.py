"""Listings API tests."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from carcatcher.db.engine import get_engine
from carcatcher.db.models import Listing


def _seed(session: Session) -> None:
    session.add_all(
        [
            Listing(
                source="kleinanzeigen", source_id="1", url="u1",
                raw_title="VW Golf", make="Volkswagen", model="Golf",
                price=4300, year=2005, mileage_km=112000,
            ),
            Listing(
                source="kleinanzeigen", source_id="2", url="u2",
                raw_title="Mercedes Citan", make="Mercedes-Benz", model="Citan",
                price=7800, year=2013, mileage_km=193000,
            ),
            Listing(
                source="kleinanzeigen", source_id="3", url="u3",
                raw_title="Sold Car", status="gone", price=1000, year=2000,
            ),
        ]
    )
    session.commit()


def test_list_excludes_gone_by_default(client):
    with Session(get_engine()) as s:
        _seed(s)
    resp = client.get("/api/listings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert all(item["status"] == "active" for item in body["items"])


def test_filter_by_price_max(client):
    with Session(get_engine()) as s:
        _seed(s)
    resp = client.get("/api/listings", params={"price_max": 5000})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["make"] == "Volkswagen"


def test_sort_by_price_asc(client):
    with Session(get_engine()) as s:
        _seed(s)
    resp = client.get("/api/listings", params={"sort": "price", "order": "asc"})
    prices = [i["price"] for i in resp.json()["items"]]
    assert prices == sorted(prices)


def test_get_single_listing_and_404(client):
    with Session(get_engine()) as s:
        _seed(s)
    ok = client.get("/api/listings/1")
    assert ok.status_code == 200
    assert ok.json()["make"] == "Volkswagen"
    missing = client.get("/api/listings/999")
    assert missing.status_code == 404


def _seed_specs(session: Session) -> None:
    """Listings exercising the power/fair-price/location/km-per-year filters."""
    this_year = datetime.now().year
    session.add_all(
        [
            Listing(
                source="kleinanzeigen", source_id="p1", url="up1",
                raw_title="Low-power city car", power_kw=60,
                fair_price_estimate=10000, location_city="Berlin",
                year=this_year - 5, mileage_km=50000,  # 10k/yr
            ),
            Listing(
                source="kleinanzeigen", source_id="p2", url="up2",
                raw_title="High-power hauler", power_kw=150,
                fair_price_estimate=30000, location_city="München",
                location_plz="80331", year=this_year - 5, mileage_km=150000,  # 30k/yr
            ),
        ]
    )
    session.commit()


def test_filter_by_power_kw_min(client):
    with Session(get_engine()) as s:
        _seed_specs(s)
    body = client.get("/api/listings", params={"power_kw_min": 100}).json()
    assert body["total"] == 1
    assert body["items"][0]["power_kw"] == 150


def test_filter_by_fair_price_max(client):
    with Session(get_engine()) as s:
        _seed_specs(s)
    body = client.get("/api/listings", params={"fair_price_max": 20000}).json()
    assert body["total"] == 1
    assert body["items"][0]["fair_price_estimate"] == 10000


def test_filter_by_location_substring_case_insensitive(client):
    with Session(get_engine()) as s:
        _seed_specs(s)
    body = client.get("/api/listings", params={"location": "berl"}).json()
    assert body["total"] == 1
    assert body["items"][0]["location_city"] == "Berlin"
    # Matches PLZ too.
    plz = client.get("/api/listings", params={"location": "80331"}).json()
    assert plz["total"] == 1
    assert plz["items"][0]["location_city"] == "München"


def test_filter_by_variant_substring_case_insensitive(client):
    with Session(get_engine()) as s:
        s.add_all(
            [
                Listing(source="kleinanzeigen", source_id="v1", url="uv1",
                        raw_title="ID.4 Pro", model="ID.4", variant="Pro Performance"),
                Listing(source="kleinanzeigen", source_id="v2", url="uv2",
                        raw_title="ID.3 Pro S", model="ID.3", variant="Pro S"),
                Listing(source="kleinanzeigen", source_id="v3", url="uv3",
                        raw_title="ID.4 GTX", model="ID.4", variant="GTX"),
            ]
        )
        s.commit()
    body = client.get("/api/listings", params={"variant": "pro"}).json()
    variants = sorted(i["variant"] for i in body["items"])
    assert variants == ["Pro Performance", "Pro S"]  # GTX excluded, case-insensitive


def test_filter_by_km_per_year_max(client):
    with Session(get_engine()) as s:
        _seed_specs(s)
    # 10k/yr car passes a 20k/yr cap; the 30k/yr car is excluded.
    body = client.get("/api/listings", params={"km_per_year_max": 20000}).json()
    assert body["total"] == 1
    assert body["items"][0]["mileage_km"] == 50000
