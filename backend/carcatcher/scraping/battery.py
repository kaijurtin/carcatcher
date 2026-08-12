"""Extracts battery capacity (kWh) embedded in free-text trim/title strings,
e.g. "Pro 82 kWh" — neither source exposes it as a structured field."""

from __future__ import annotations

import re

_BATTERY_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*kWh", re.IGNORECASE)


def parse_battery_kwh(*texts: str | None) -> float | None:
    """Return the first "NN[.,N] kWh" match found across `texts`, checked in
    order, or None if none of them contain one."""
    for text in texts:
        if not text:
            continue
        match = _BATTERY_RE.search(text)
        if match:
            return float(match.group(1).replace(",", "."))
    return None
