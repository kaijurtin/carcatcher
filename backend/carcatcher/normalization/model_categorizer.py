"""Deterministic model categorizer for VW ID listings.

Applies correct manufacturer model naming + nominal battery spec to listings using
the rules in `vw_id_specs`, with no AI. Two roles:

1. Canonicalize Haiku output ("ID 4 Pro" -> model "ID.4", variant "Pro").
2. Serve as the structured-field provider when AI normalization is switched off —
   in that mode make/model are empty, so the model is detected from the raw title.

Non-destructive, mirroring `apply_normalized`: it canonicalizes the model name and
gap-fills empty fields, but never overwrites a populated, plausible variant or an
already-sensible battery value (only snaps a near-spec value to the canonical one).
Only Volkswagen ID models are recognized; everything else is a no-op. The registry
is keyed by canonical make so other makes can be added later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from carcatcher.db.models import Listing
from carcatcher.normalization.makes import canonical_make
from carcatcher.normalization.vw_id_specs import VW_ID_MODELS, ModelSpec, TrimSpec

# Matches the model token in "ID.4" / "ID 4" / "id4" / "ID. Buzz" / "idbuzz".
# The leading \b stops mid-word hits (e.g. "covid", "raid").
_ID_RE = re.compile(r"\bid[\s.]*(buzz|[3-7])", re.IGNORECASE)

# A present battery value within this tolerance of a spec capacity is snapped to it.
_SNAP_TOL_KWH = 1.5
# Year slack outside the documented production range before we refuse to fill battery.
_YEAR_SLACK = 1


@dataclass
class CategoryResult:
    make: str | None = None
    model: str | None = None
    variant: str | None = None
    battery_kwh: float | None = None
    matched: bool = False  # True only when a VW ID model was recognized


def _norm(*parts: str | None) -> str:
    """Lowercased, single-spaced join of the given text fragments."""
    return re.sub(r"\s+", " ", " ".join(p for p in parts if p).lower()).strip()


def _match_trim(spec: ModelSpec, text: str) -> TrimSpec | None:
    """Find the trim whose alias appears in `text`, preferring the longest alias
    (so "pro s" wins over "pro", "pure performance" over "pure")."""
    candidates: list[tuple[int, TrimSpec, str]] = [
        (len(alias), trim, alias) for trim in spec.trims for alias in trim.aliases
    ]
    candidates.sort(key=lambda c: c[0], reverse=True)
    for _, trim, alias in candidates:
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return trim
    return None


def _resolve_battery(
    spec: ModelSpec, trim: TrimSpec | None, year: int | None, battery_kwh: float | None
) -> float | None:
    """Canonical usable kWh for this listing, or None to leave it unchanged.

    Present value -> snap to a spec capacity only if within tolerance, else keep.
    Missing value -> fill from the trim (when unambiguous) or the model (when it has
    a single capacity), and only when the year is plausible for this model.
    """
    if battery_kwh is not None:
        nearest = min(spec.capacities, key=lambda c: abs(c - battery_kwh))
        return nearest if abs(nearest - battery_kwh) <= _SNAP_TOL_KWH else battery_kwh

    lo, hi = spec.year_range
    if year is not None and not (lo - _YEAR_SLACK <= year <= hi + _YEAR_SLACK):
        return None
    if trim is not None and trim.fill_kwh is not None:
        return trim.fill_kwh
    if len(spec.capacities) == 1:
        return spec.capacities[0]
    return None


def categorize(
    make: str | None,
    model: str | None,
    variant: str | None,
    year: int | None,
    battery_kwh: float | None,
    *,
    text: str | None = None,
) -> CategoryResult:
    """Categorize one listing's fields. `text` (e.g. the raw title) is searched in
    addition to model/variant so detection works when AI left those empty."""
    cm = canonical_make(make)
    if cm is not None and cm != "Volkswagen":
        return CategoryResult()  # explicitly another make — not ours

    haystack = _norm(model, variant, text)
    m = _ID_RE.search(haystack)
    if m is None:
        return CategoryResult()

    spec = VW_ID_MODELS.get(m.group(1).lower())
    if spec is None:
        return CategoryResult()

    trim = _match_trim(spec, haystack)
    return CategoryResult(
        make="Volkswagen",
        model=spec.canonical,
        variant=trim.name if trim is not None else None,
        battery_kwh=_resolve_battery(spec, trim, year, battery_kwh),
        matched=True,
    )


def apply_categorization(listing: Listing) -> bool:
    """Apply categorization in place. Returns True if any field changed.

    Canonicalizes make/model; gap-fills variant and battery without clobbering a
    populated variant or overriding a battery value that isn't near a known spec.
    No-op when the user has locked the model via a manual reassignment.
    """
    if listing.model_locked:
        return False
    result = categorize(
        listing.make,
        listing.model,
        listing.variant,
        listing.year,
        listing.battery_kwh,
        text=listing.raw_title,
    )
    if not result.matched:
        return False

    changed = False
    if result.make and listing.make != result.make:
        listing.make = result.make
        changed = True
    if result.model and listing.model != result.model:
        listing.model = result.model
        changed = True
    # Gap-fill only: never clobber a variant Haiku was confident about.
    if result.variant and not listing.variant:
        listing.variant = result.variant
        changed = True
    if result.battery_kwh is not None and result.battery_kwh != listing.battery_kwh:
        listing.battery_kwh = result.battery_kwh
        changed = True
    return changed
