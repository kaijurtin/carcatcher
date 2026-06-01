"""Favorites: API endpoints, favorites_only filter, is_favorite flag, prune survival."""

from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session, select

from carcatcher.db.engine import get_engine
from carcatcher.db.models import Favorite, Listing, ListingStatus
from carcatcher.pipeline.snapshot import prune


def _seed(session: Session) -> list[int]:
    rows = [
        Listing(source="autoscout24", source_id="a1", url="a1", raw_title="VW ID.4"),
        Listing(source="autoscout24", source_id="a2", url="a2", raw_title="VW ID.3"),
    ]
    session.add_all(rows)
    session.commit()
    return [r.id for r in session.exec(select(Listing)).all()]


def test_put_favorite_then_listing_shows_is_favorite(client):
    with Session(get_engine()) as s:
        ids = _seed(s)

    assert client.put(f"/api/listings/{ids[0]}/favorite").status_code == 204
    body = client.get("/api/listings").json()
    by_id = {i["id"]: i for i in body["items"]}
    assert by_id[ids[0]]["is_favorite"] is True
    assert by_id[ids[1]]["is_favorite"] is False


def test_favorites_only_filter(client):
    with Session(get_engine()) as s:
        ids = _seed(s)
    client.put(f"/api/listings/{ids[1]}/favorite")
    r = client.get("/api/listings", params={"favorites_only": True})
    assert {i["id"] for i in r.json()["items"]} == {ids[1]}


def test_delete_clears_favorite(client):
    with Session(get_engine()) as s:
        ids = _seed(s)
    client.put(f"/api/listings/{ids[0]}/favorite")
    assert client.delete(f"/api/listings/{ids[0]}/favorite").status_code == 204
    r = client.get("/api/listings", params={"favorites_only": True})
    assert r.json()["items"] == []


def test_double_put_is_idempotent(client):
    with Session(get_engine()) as s:
        ids = _seed(s)
    client.put(f"/api/listings/{ids[0]}/favorite")
    client.put(f"/api/listings/{ids[0]}/favorite")
    with Session(get_engine()) as s:
        favs = s.exec(select(Favorite).where(Favorite.listing_id == ids[0])).all()
        assert len(favs) == 1


def test_favorite_on_missing_listing_404(client):
    with Session(get_engine()):
        pass
    assert client.put("/api/listings/9999/favorite").status_code == 404


def test_prune_keeps_favorited_gone_listing(test_engine):
    # A gone, unlinked listing would normally be pruned — a favorite must protect it.
    with Session(get_engine()) as s:
        li = Listing(
            source="kleinanzeigen", source_id="g1", url="g1", raw_title="VW ID.4",
            status=ListingStatus.GONE.value,
        )
        s.add(li)
        s.commit()
        s.refresh(li)
        s.add(Favorite(listing_id=li.id))
        s.commit()

        deleted = prune(s, prune_gone_days=0)  # cutoff in the past -> prune everything eligible
        assert deleted == 0
        assert s.get(Listing, li.id) is not None
