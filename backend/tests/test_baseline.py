"""Statistical baseline tests: comparables, fair-price math, gate/widening."""

from __future__ import annotations

from sqlmodel import Session

from carcatcher.db.engine import get_engine
from carcatcher.db.models import Listing
from carcatcher.scoring.baseline import (
    compute_fair_price,
    evaluate_baseline,
    find_comparables,
)


def _listing(sid: str, **over) -> Listing:
    base = dict(
        source="kleinanzeigen", source_id=sid, url=f"u{sid}",
        make="Volkswagen", model="Golf", price=10000, mileage_km=100000, year=2015,
    )
    base.update(over)
    return Listing(**base)


def _seed(session: Session, listings: list[Listing]) -> None:
    session.add_all(listings)
    session.commit()


def test_compute_fair_price_median_no_adjustment():
    comps = [_listing(str(i), price=10000, mileage_km=100000, year=2015) for i in range(3)]
    fair = compute_fair_price(100000, 2015, comps)
    assert fair == 10000


def test_compute_fair_price_lower_mileage_raises_value():
    comps = [_listing(str(i), price=10000, mileage_km=100000, year=2015) for i in range(3)]
    # 20k km below median -> +12% (6e-6 * 20000)
    fair = compute_fair_price(80000, 2015, comps)
    assert fair == 11200


def test_compute_fair_price_clamped():
    comps = [_listing(str(i), price=10000, mileage_km=100000, year=2015) for i in range(3)]
    # 0 km vs 100k median -> +60% raw, clamped to +30%
    fair = compute_fair_price(0, 2015, comps)
    assert fair == 13000


def test_find_comparables_respects_bands(test_engine):
    with Session(get_engine()) as s:
        target = _listing("T", price=9000)
        in_band = _listing("A", price=10000, mileage_km=110000, year=2016)
        out_year = _listing("B", price=10000, mileage_km=100000, year=2010)
        out_km = _listing("C", price=10000, mileage_km=200000, year=2015)
        other_model = _listing("D", model="Passat")
        _seed(s, [target, in_band, out_year, out_km, other_model])

        comps = find_comparables(s, target, year_window=1, mileage_pct=0.25, match_variant=False)
        ids = {c.source_id for c in comps}
        assert ids == {"A"}  # B out of year, C out of km, D wrong model, T is self


def test_evaluate_baseline_computes_deal(test_engine):
    with Session(get_engine()) as s:
        target = _listing("T", price=9000, mileage_km=100000, year=2015)
        comps = [_listing(str(i), price=10000, mileage_km=100000, year=2015) for i in range(3)]
        _seed(s, [target, *comps])

        result = evaluate_baseline(s, target, min_comps=3)
        assert result.fair_price_estimate == 10000
        assert result.comp_count == 3
        assert result.deal_score == 0.1  # 10% below fair


def test_widening_when_narrow_too_few(test_engine):
    with Session(get_engine()) as s:
        target = _listing("T", price=9000, year=2015, mileage_km=100000)
        # All comps are 2 years off + 35% higher km: outside narrow, inside wide.
        comps = [
            _listing(str(i), price=10000, year=2017, mileage_km=135000)
            for i in range(3)
        ]
        _seed(s, [target, *comps])

        narrow = find_comparables(s, target, year_window=1, mileage_pct=0.25, match_variant=True)
        assert len(narrow) == 0
        result = evaluate_baseline(s, target, min_comps=3)
        assert result.comp_count == 3  # found via widening
        assert result.fair_price_estimate is not None


def test_insufficient_comps_returns_none(test_engine):
    with Session(get_engine()) as s:
        target = _listing("T", price=9000)
        _seed(s, [target, _listing("A", price=10000)])  # only 1 comp
        result = evaluate_baseline(s, target, min_comps=3)
        assert result.fair_price_estimate is None
        assert result.deal_score is None
        assert result.comp_count == 1


def test_not_scoreable_without_price(test_engine):
    with Session(get_engine()) as s:
        target = _listing("T", price=None)
        _seed(s, [target])
        result = evaluate_baseline(s, target, min_comps=3)
        assert result.fair_price_estimate is None
        assert result.comp_count == 0
