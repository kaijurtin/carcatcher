"""Statistical fair-price baseline.

For a listing, find comparables in the current active snapshot (same make+model,
similar year/mileage), take the median price, and adjust for this car's mileage and
age. `deal_score = (fair - price) / fair` (positive = priced below fair = good deal).
KISS for personal scale (hundreds–low-thousands of listings).
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from sqlmodel import Session, select

from carcatcher.db.models import Listing, ListingStatus, utcnow

# Adjustment coefficients (clamped). ~6% per 10k km vs. median, ~4% per model year.
_MILEAGE_COEF_PER_KM = 6e-6
_YEAR_COEF = 0.04
_CLAMP_LOW, _CLAMP_HIGH = 0.7, 1.3

# Comparable bands: narrow first, then a single widening pass.
_NARROW = dict(year_window=1, mileage_pct=0.25, match_variant=True)
_WIDE = dict(year_window=2, mileage_pct=0.40, match_variant=False)


@dataclass
class BaselineResult:
    fair_price_estimate: int | None
    deal_score: float | None
    comp_count: int


def _scoreable(listing: Listing) -> bool:
    return (
        listing.price is not None
        and listing.mileage_km is not None
        and listing.year is not None
        and bool(listing.make)
        and bool(listing.model)
    )


def find_comparables(
    session: Session,
    listing: Listing,
    *,
    year_window: int,
    mileage_pct: float,
    match_variant: bool,
) -> list[Listing]:
    """Active listings comparable to `listing` (excludes itself)."""
    lo_km = int(listing.mileage_km * (1 - mileage_pct))
    hi_km = int(listing.mileage_km * (1 + mileage_pct))
    conditions = [
        Listing.id != listing.id,
        Listing.status == ListingStatus.ACTIVE.value,
        Listing.make == listing.make,
        Listing.model == listing.model,
        Listing.price.is_not(None),  # type: ignore[union-attr]
        Listing.mileage_km.is_not(None),  # type: ignore[union-attr]
        Listing.year.is_not(None),  # type: ignore[union-attr]
        Listing.year >= listing.year - year_window,
        Listing.year <= listing.year + year_window,
        Listing.mileage_km >= lo_km,
        Listing.mileage_km <= hi_km,
    ]
    if match_variant and listing.variant:
        conditions.append(Listing.variant == listing.variant)
    return list(session.exec(select(Listing).where(*conditions)).all())


def compute_fair_price(mileage_km: int, year: int, comps: list[Listing]) -> int:
    """Median comparable price adjusted for this car's mileage/age (clamped)."""
    prices = [c.price for c in comps]
    m = median(prices)
    km_med = median([c.mileage_km for c in comps])
    y_med = median([c.year for c in comps])
    factor = (1 + _MILEAGE_COEF_PER_KM * (km_med - mileage_km)) * (
        1 + _YEAR_COEF * (year - y_med)
    )
    factor = max(_CLAMP_LOW, min(_CLAMP_HIGH, factor))
    return int(round(m * factor))


def evaluate_baseline(
    session: Session, listing: Listing, *, min_comps: int
) -> BaselineResult:
    """Compute the fair-price baseline + deal score for one listing."""
    if not _scoreable(listing):
        return BaselineResult(None, None, 0)

    comps = find_comparables(session, listing, **_NARROW)
    if len(comps) < min_comps:
        comps = find_comparables(session, listing, **_WIDE)
    if len(comps) < min_comps:
        return BaselineResult(None, None, len(comps))

    fair = compute_fair_price(listing.mileage_km, listing.year, comps)
    deal = round((fair - listing.price) / fair, 3) if fair > 0 else None
    return BaselineResult(fair, deal, len(comps))


def score_listing(session: Session, listing: Listing, *, min_comps: int) -> BaselineResult:
    """Evaluate + persist the baseline onto the listing."""
    result = evaluate_baseline(session, listing, min_comps=min_comps)
    listing.fair_price_estimate = result.fair_price_estimate
    listing.deal_score = result.deal_score
    listing.comp_count = result.comp_count
    listing.scored_at = utcnow()
    session.add(listing)
    return result
