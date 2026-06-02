"""Manual model reassignment: PATCH locks the model; AI steps then leave it alone."""

from __future__ import annotations

from sqlmodel import Session, select

from carcatcher.api.routes.listings import ListingRead
from carcatcher.db.engine import get_engine
from carcatcher.db.models import Listing
from carcatcher.normalization.model_categorizer import apply_categorization
from carcatcher.normalization.schema import NormalizedListing
from carcatcher.pipeline.normalize import apply_normalized


def _seed(session: Session) -> int:
    li = Listing(
        source="autoscout24", source_id="r1", url="r1",
        raw_title="VW ID 4 Pro", make="Volkswagen", model="ID.4",
    )
    session.add(li)
    session.commit()
    return li.id


def test_patch_sets_model_and_locks(client):
    with Session(get_engine()) as s:
        lid = _seed(s)

    resp = client.patch(f"/api/listings/{lid}/model", json={"model": "ID.5 GTX"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["model"] == "ID.5 GTX"
    assert body["model_locked"] is True

    with Session(get_engine()) as s:
        assert s.get(Listing, lid).model == "ID.5 GTX"


def test_listing_read_coerces_null_model_locked(client):
    # Regression: a column added via ALTER on existing prod rows reads as NULL;
    # ListingRead must coerce NULL model_locked -> False instead of 500-ing /api/listings.
    with Session(get_engine()) as s:
        lid = _seed(s)
        li = s.get(Listing, lid)
        li.model_locked = None  # simulate the ALTER-added NULL value
        out = ListingRead.model_validate(li)
        assert out.model_locked is False


def test_patch_404_for_missing_listing(client):
    assert client.patch("/api/listings/9999/model", json={"model": "X"}).status_code == 404


def test_patch_rejects_blank_model(client):
    with Session(get_engine()) as s:
        lid = _seed(s)
    assert client.patch(f"/api/listings/{lid}/model", json={"model": "  "}).status_code == 422


def test_apply_normalized_does_not_overwrite_locked_model(client):
    with Session(get_engine()) as s:
        lid = _seed(s)
    client.patch(f"/api/listings/{lid}/model", json={"model": "Custom Model"})

    with Session(get_engine()) as s:
        listing = s.get(Listing, lid)
        norm = NormalizedListing(make="Volkswagen", model="ID.4", variant="Pro")
        apply_normalized(listing, norm)
        # Locked model + variant untouched; other AI fields still applied.
        assert listing.model == "Custom Model"
        assert listing.variant is None  # variant is locked too
        assert listing.make == "Volkswagen"


def test_apply_categorization_skips_locked_model(client):
    with Session(get_engine()) as s:
        lid = _seed(s)
    client.patch(f"/api/listings/{lid}/model", json={"model": "Custom Model"})

    with Session(get_engine()) as s:
        listing = s.get(Listing, lid)
        changed = apply_categorization(listing)
        assert changed is False
        assert listing.model == "Custom Model"
