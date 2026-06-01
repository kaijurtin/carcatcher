"""Tests for make/model match filtering of saved-search tabs.

A crawl tags EVERY scraped listing to the search unconditionally (source
"related ads" included), so a search tab must re-check each listing's
normalized make/model against the search's own criteria before showing it.
"""

from __future__ import annotations

from sqlmodel import Session

from carcatcher.db.engine import get_engine
from carcatcher.db.models import ListingSearch, ListingStatus, Listing, SavedSearch
from carcatcher.normalization.makes import canonical_make


# --------------------------------------------------------------------------- #
# canonical_make
# --------------------------------------------------------------------------- #
def test_canonical_make_aliases_vw_to_volkswagen():
    assert canonical_make("VW") == "Volkswagen"
    assert canonical_make("vw") == "Volkswagen"
    assert canonical_make("volkswagen") == "Volkswagen"


def test_canonical_make_aliases_mercedes():
    assert canonical_make("MB") == "Mercedes-Benz"
    assert canonical_make("Merc") == "Mercedes-Benz"


def test_canonical_make_keeps_unknown_and_handles_none():
    assert canonical_make("Opel") == "Opel"
    assert canonical_make("  vw ") == "Volkswagen"
    assert canonical_make(None) is None
    assert canonical_make("") is None


# --------------------------------------------------------------------------- #
# match filtering via /api/listings?search_id=...
# --------------------------------------------------------------------------- #
def _tag(s: Session, search_id: int, listing: Listing) -> None:
    s.add(listing)
    s.commit()
    s.refresh(listing)
    s.add(
        ListingSearch(
            search_id=search_id,
            listing_id=listing.id,
            status=ListingStatus.ACTIVE.value,
        )
    )
    s.commit()


def _seed_search_with_mixed_listings(s: Session) -> int:
    search = SavedSearch(name="VW ID.4", criteria={"make": "VW", "model": "ID.4"})
    s.add(search)
    s.commit()
    s.refresh(search)
    # matches (normalizer emits canonical "Volkswagen")
    _tag(s, search.id, Listing(
        source="kleinanzeigen", source_id="m1", url="http://m1",
        status=ListingStatus.ACTIVE.value, make="Volkswagen", model="ID.4",
    ))
    # wrong make/model — a "related ad" that got tagged
    _tag(s, search.id, Listing(
        source="kleinanzeigen", source_id="b1", url="http://b1",
        status=ListingStatus.ACTIVE.value, make="BMW", model="3er",
    ))
    # not-yet-normalized (NULL make/model)
    _tag(s, search.id, Listing(
        source="kleinanzeigen", source_id="n1", url="http://n1",
        status=ListingStatus.ACTIVE.value, make=None, model=None,
    ))
    return search.id


def test_search_tab_shows_only_matching_make_model(client):
    with Session(get_engine()) as s:
        sid = _seed_search_with_mixed_listings(s)
    resp = client.get("/api/listings", params={"search_id": sid, "status": "all"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["source_id"] == "m1"
    assert body["items"][0]["make"] == "Volkswagen"


def test_search_without_make_model_criteria_shows_all_tagged(client):
    with Session(get_engine()) as s:
        search = SavedSearch(name="cheap EVs", criteria={"price_max": 30000})
        s.add(search)
        s.commit()
        s.refresh(search)
        sid = search.id
        _tag(s, sid, Listing(
            source="k", source_id="a", url="http://a",
            status=ListingStatus.ACTIVE.value, make="Volkswagen", model="ID.4",
        ))
        _tag(s, sid, Listing(
            source="k", source_id="b", url="http://b",
            status=ListingStatus.ACTIVE.value, make="BMW", model="i3",
        ))
    resp = client.get("/api/listings", params={"search_id": sid, "status": "all"})
    assert resp.json()["total"] == 2
