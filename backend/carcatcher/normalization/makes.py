"""Canonical manufacturer names.

Mirrors the make-normalization rules stated in the Haiku prompt
(`normalization/prompts.py`) so the same aliasing can be reused in code — e.g.
matching a saved search's stored `make` (which may be "VW") against listings the
normalizer emits as canonical ("Volkswagen").
"""

from __future__ import annotations

# Lowercased alias -> canonical make (as the normalizer emits it).
_MAKE_ALIASES: dict[str, str] = {
    "vw": "Volkswagen",
    "volkswagen": "Volkswagen",
    "mb": "Mercedes-Benz",
    "merc": "Mercedes-Benz",
    "mercedes": "Mercedes-Benz",
    "mercedes-benz": "Mercedes-Benz",
}


def canonical_make(value: str | None) -> str | None:
    """Map a manufacturer name/abbreviation to its canonical form.

    Comparison elsewhere is case-insensitive, so an unknown make is returned
    stripped-but-unchanged rather than reshaped. Empty/None -> None.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return _MAKE_ALIASES.get(stripped.lower(), stripped)
