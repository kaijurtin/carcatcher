"""Score pipeline step tests."""

from __future__ import annotations

from sqlmodel import Session, select

from carcatcher.db.engine import get_engine
from carcatcher.db.models import Listing, ListingStatus
from carcatcher.pipeline.score import score_active


def _listing(sid: str, **over) -> Listing:
    base = dict(
        source="kleinanzeigen", source_id=sid, url=f"u{sid}",
        make="Volkswagen", model="Golf", price=10000, mileage_km=100000, year=2015,
    )
    base.update(over)
    return Listing(**base)


def test_score_active_sets_baseline_for_all(test_engine):
    # 1 target priced low + 5 comps at 10000 (default MIN_COMPS=5).
    with Session(get_engine()) as s:
        target = _listing("T", price=8000)
        comps = [_listing(str(i)) for i in range(5)]
        s.add_all([target, *comps])
        s.commit()

        stats = score_active(s)
        assert stats.scored == 6
        scored_target = s.exec(select(Listing).where(Listing.source_id == "T")).one()
        assert scored_target.fair_price_estimate == 10000
        assert scored_target.deal_score == 0.2  # 20% under fair
        assert scored_target.comp_count == 5
        assert stats.deals >= 1  # target beats the 8% threshold


def test_score_active_ignores_gone(test_engine):
    with Session(get_engine()) as s:
        s.add(_listing("G", status=ListingStatus.GONE.value))
        s.commit()
        stats = score_active(s)
        assert stats.scored == 0  # gone listing not scored
