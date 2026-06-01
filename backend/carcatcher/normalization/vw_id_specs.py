"""Reference data for Volkswagen ID. electric models.

Pure-Python lookup table (no I/O) used by `model_categorizer` to apply correct
manufacturer model naming and fill the nominal usable battery capacity (kWh) for
VW ID listings — both to canonicalize Haiku output and to populate fields when AI
normalization is switched off.

`capacities` are *usable* (net) pack sizes in kWh, the same quantity Haiku is asked
to extract for `battery_kwh`. A trim's `fill_kwh` is set only when that
(model, trim) pair maps unambiguously to a single usable capacity across its
production years — otherwise it stays None and the categorizer leaves the field
alone rather than guessing. `battery_kwh` here is the *nominal spec*, distinct from
a used car's State of Health (degradation).

Sources (verified 2026-06):
- en.wikipedia.org/wiki/Volkswagen_ID.3 — 45 / 58 / 77 (early), 52 / 59 / 79 (2023+).
- en.wikipedia.org/wiki/Volkswagen_ID._Buzz — 77 / 79 / 86 usable by version.
- volkswagen-newsroom.com (ID.7 Pro S 86 kWh net); ID.7 Pro 77 kWh net.
- ev-database.org, batterydesign.net (ID.4/ID.5 52 / 77, GTX 77; 79 from 2024 packs).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrimSpec:
    """A canonical trim/variant and the listing text that maps to it."""

    name: str  # canonical variant, e.g. "Pro S"
    aliases: tuple[str, ...]  # normalized (lowercased) trim phrases that resolve here
    fill_kwh: float | None = None  # usable kWh to fill when unambiguous; else None


@dataclass(frozen=True)
class ModelSpec:
    """A VW ID model, keyed by the digit/word in its name (3/4/5/7/buzz)."""

    canonical: str  # display name, e.g. "ID.4"
    key: str  # regex capture token: "3" / "4" / "5" / "7" / "buzz"
    year_range: tuple[int, int]  # inclusive production years (slack applied by caller)
    capacities: tuple[float, ...]  # all plausible usable kWh (for snap + plausibility)
    trims: tuple[TrimSpec, ...]


# Common trim phrases. "Pro S" / "Pure Performance" must be matched before the
# shorter "Pro" / "Pure" — the categorizer scans longest-alias-first.
_PURE = TrimSpec("Pure", ("pure performance", "pure"))
_PRO = TrimSpec("Pro", ("pro performance", "pro"))
_PRO_S = TrimSpec("Pro S", ("pro s", "pros"))


VW_ID_MODELS: dict[str, ModelSpec] = {
    "3": ModelSpec(
        canonical="ID.3",
        key="3",
        year_range=(2020, 2026),
        capacities=(45.0, 52.0, 58.0, 59.0, 77.0, 79.0),
        trims=(
            _PURE,
            _PRO,
            _PRO_S,
            TrimSpec("Tour", ("tour",)),
            TrimSpec("GTX", ("gtx performance", "gtx"), fill_kwh=79.0),
        ),
    ),
    "4": ModelSpec(
        canonical="ID.4",
        key="4",
        year_range=(2020, 2026),
        capacities=(52.0, 59.0, 77.0, 79.0),
        trims=(
            _PURE,
            _PRO,
            _PRO_S,
            TrimSpec("GTX", ("gtx performance", "gtx"), fill_kwh=77.0),
        ),
    ),
    "5": ModelSpec(
        canonical="ID.5",
        key="5",
        year_range=(2021, 2026),
        capacities=(77.0, 79.0),
        trims=(
            _PRO,
            _PRO_S,
            TrimSpec("GTX", ("gtx performance", "gtx"), fill_kwh=77.0),
        ),
    ),
    "7": ModelSpec(
        canonical="ID.7",
        key="7",
        year_range=(2023, 2026),
        capacities=(77.0, 86.0),
        trims=(
            TrimSpec("Pro", ("pro performance", "pro"), fill_kwh=77.0),
            TrimSpec("Pro S", ("pro s", "pros"), fill_kwh=86.0),
            TrimSpec("GTX", ("gtx performance", "gtx"), fill_kwh=86.0),
        ),
    ),
    "buzz": ModelSpec(
        canonical="ID. Buzz",
        key="buzz",
        year_range=(2022, 2026),
        capacities=(77.0, 79.0, 86.0),
        trims=(
            _PRO,
            _PRO_S,
            TrimSpec("GTX", ("gtx performance", "gtx")),
            TrimSpec("Cargo", ("cargo",)),
        ),
    ),
}
