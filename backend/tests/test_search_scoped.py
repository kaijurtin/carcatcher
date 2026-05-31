"""Search-scoped feature tests: enabled flag, /run endpoint, cascade delete,
and the search_id listing filter."""

from __future__ import annotations

import carcatcher.api.routes.saved_searches as ss_mod
from sqlmodel import Session, select

from carcatcher.db.engine import get_engine
from carcatcher.db.models import (
    CrawlRun,
    Listing,
    ListingSearch,
    RunStatus,
    SavedSearch,
    Shortlist,
    ShortlistItem,
)


# --- enabled in CRUD -------------------------------------------------------- #
def test_enabled_create_and_toggle(client):
    r = client.post("/api/saved-searches", json={"name": "x", "enabled": False})
    assert r.status_code == 201
    sid = r.json()["id"]
    assert r.json()["enabled"] is False
    r = client.put(f"/api/saved-searches/{sid}", json={"enabled": True})
    assert r.json()["enabled"] is True


# --- /run endpoint ---------------------------------------------------------- #
def test_run_endpoint_requires_secret(client):
    with Session(get_engine()) as s:
        s.add(SavedSearch(name="x"))
        s.commit()
    assert client.post("/api/saved-searches/1/run").status_code == 401
    assert client.post(
        "/api/saved-searches/1/run", headers={"X-Cron-Secret": "wrong"}
    ).status_code == 401


def test_run_endpoint_404_missing(client):
    assert client.post(
        "/api/saved-searches/999/run", headers={"X-Cron-Secret": "test-secret"}
    ).status_code == 404


def test_run_endpoint_409_when_running(client):
    with Session(get_engine()) as s:
        s.add(SavedSearch(name="x"))
        s.add(CrawlRun(source="x", status=RunStatus.RUNNING.value))
        s.commit()
    resp = client.post("/api/saved-searches/1/run", headers={"X-Cron-Secret": "test-secret"})
    assert resp.status_code == 409


def test_run_endpoint_202_schedules(client, monkeypatch):
    called = {}

    async def fake_run_search(search_id, **kwargs):
        called["id"] = search_id

    monkeypatch.setattr(ss_mod, "run_search", fake_run_search)
    with Session(get_engine()) as s:
        s.add(SavedSearch(name="x"))
        s.commit()
    resp = client.post("/api/saved-searches/1/run", headers={"X-Cron-Secret": "test-secret"})
    assert resp.status_code == 202


# --- cascade delete --------------------------------------------------------- #
def test_delete_cascades_to_listings(client):
    with Session(get_engine()) as s:
        s.add(SavedSearch(name="x"))  # id 1
        li_orphan = Listing(source="k", source_id="1", url="u1")
        li_short = Listing(source="k", source_id="2", url="u2")
        s.add_all([li_orphan, li_short])
        s.commit()
        s.refresh(li_orphan)
        s.refresh(li_short)
        s.add_all([
            ListingSearch(search_id=1, listing_id=li_orphan.id),
            ListingSearch(search_id=1, listing_id=li_short.id),
        ])
        sl = Shortlist(name="default")
        s.add(sl)
        s.commit()
        s.add(ShortlistItem(shortlist_id=sl.id, listing_id=li_short.id))
        s.commit()

    assert client.delete("/api/saved-searches/1").status_code == 204
    with Session(get_engine()) as s:
        assert s.exec(select(ListingSearch)).all() == []   # links removed
        remaining = {x.source_id for x in s.exec(select(Listing)).all()}
        assert remaining == {"2"}  # orphan deleted, shortlisted kept


# --- search_id listing filter ----------------------------------------------- #
def test_listings_filter_by_search_id(client):
    with Session(get_engine()) as s:
        s.add_all([SavedSearch(name="A"), SavedSearch(name="B")])
        a = Listing(source="k", source_id="1", url="u1", make="VW")
        b = Listing(source="k", source_id="2", url="u2", make="BMW")
        s.add_all([a, b])
        s.commit()
        s.refresh(a)
        s.refresh(b)
        s.add_all([
            ListingSearch(search_id=1, listing_id=a.id),   # only A sees the VW
            ListingSearch(search_id=2, listing_id=b.id),   # only B sees the BMW
        ])
        s.commit()

    only_a = client.get("/api/listings", params={"search_id": 1}).json()
    assert only_a["total"] == 1 and only_a["items"][0]["make"] == "VW"
    only_b = client.get("/api/listings", params={"search_id": 2}).json()
    assert only_b["total"] == 1 and only_b["items"][0]["make"] == "BMW"
