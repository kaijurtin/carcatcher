"""Saved-search CRUD + auto_evaluate candidate wiring."""

from __future__ import annotations

from sqlmodel import Session

from carcatcher.config import Settings
from carcatcher.db.engine import get_engine
from carcatcher.db.models import Listing, ListingStatus, SavedSearch
from carcatcher.scoring.candidates import select_candidates


# --- CRUD via the API ------------------------------------------------------- #
def test_saved_search_crud(client):
    # create
    r = client.post(
        "/api/saved-searches",
        json={
            "name": "VW Golf budget",
            "criteria": {"make": "Volkswagen", "model": "Golf", "price_max": 15000},
            "nl_query": "cheap golf",
            "auto_evaluate": True,
        },
    )
    assert r.status_code == 201
    created = r.json()
    sid = created["id"]
    assert created["name"] == "VW Golf budget"
    assert created["criteria"]["make"] == "Volkswagen"
    assert created["auto_evaluate"] is True

    # list
    assert len(client.get("/api/saved-searches").json()) == 1

    # get
    assert client.get(f"/api/saved-searches/{sid}").json()["nl_query"] == "cheap golf"

    # update (toggle auto_evaluate + change price)
    r = client.put(
        f"/api/saved-searches/{sid}",
        json={"auto_evaluate": False, "criteria": {"make": "Volkswagen", "price_max": 9000}},
    )
    assert r.status_code == 200
    assert r.json()["auto_evaluate"] is False
    assert r.json()["criteria"]["price_max"] == 9000

    # delete
    assert client.delete(f"/api/saved-searches/{sid}").status_code == 204
    assert client.get(f"/api/saved-searches/{sid}").status_code == 404
    assert len(client.get("/api/saved-searches").json()) == 0


def test_update_missing_404(client):
    assert client.put("/api/saved-searches/999", json={"name": "x"}).status_code == 404


# --- duplicate -------------------------------------------------------------- #
def _create(client, **over) -> int:
    body = {"name": "VW ID.4", "criteria": {"make": "Volkswagen", "model": "ID.4"}}
    body.update(over)
    return client.post("/api/saved-searches", json=body).json()["id"]


def test_duplicate_clones_criteria_and_query(client):
    sid = _create(client, nl_query="VW ID.4 GTX ab 2022", auto_evaluate=True)
    r = client.post(f"/api/saved-searches/{sid}/duplicate")
    assert r.status_code == 201
    clone = r.json()
    assert clone["id"] != sid
    assert clone["name"] == "Copy of VW ID.4"
    assert clone["criteria"] == {"make": "Volkswagen", "model": "ID.4"}
    assert clone["nl_query"] == "VW ID.4 GTX ab 2022"
    assert clone["auto_evaluate"] is True
    assert len(client.get("/api/saved-searches").json()) == 2


def test_duplicate_404_for_missing(client):
    assert client.post("/api/saved-searches/999/duplicate").status_code == 404


# --- auto_evaluate candidate wiring ----------------------------------------- #
def _listing(sid: str, **over) -> Listing:
    base = dict(
        source="kleinanzeigen", source_id=sid, url=f"u{sid}",
        make="Volkswagen", model="Golf", price=9000, mileage_km=100000, year=2015,
        deal_score=None, comp_count=0, status=ListingStatus.ACTIVE.value,
    )
    base.update(over)
    return Listing(**base)


def test_auto_evaluate_search_adds_matches_as_candidates(test_engine):
    s = Settings(deal_threshold=0.08, min_comps=5, max_sonnet_evals_per_run=30)
    with Session(get_engine()) as sess:
        # A Golf (matches) with no deal score, and a BMW (doesn't match).
        sess.add_all([_listing("golf"), _listing("bmw", make="BMW", model="3er")])
        sess.commit()
        # Without an auto_evaluate search: no candidates (no deals, no shortlist).
        assert select_candidates(sess, s) == []
        # Add an auto_evaluate search for Volkswagen.
        sess.add(SavedSearch(name="vw", criteria={"make": "Volkswagen"}, auto_evaluate=True))
        sess.commit()
        ids = {c.source_id for c in select_candidates(sess, s)}
        assert ids == {"golf"}  # matched the auto_evaluate search; BMW excluded


def test_auto_evaluate_skips_already_evaluated(test_engine):
    from carcatcher.db.models import utcnow

    s = Settings(deal_threshold=0.08, min_comps=5)
    with Session(get_engine()) as sess:
        sess.add(_listing("golf", ai_evaluated_at=utcnow()))
        sess.add(SavedSearch(name="vw", criteria={"make": "Volkswagen"}, auto_evaluate=True))
        sess.commit()
        assert select_candidates(sess, s) == []
