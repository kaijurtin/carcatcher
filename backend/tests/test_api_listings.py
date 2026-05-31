"""Listings API tests."""

from __future__ import annotations

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
