"""Guide-aware variant categorization agent (VW ID only).

When the deterministic categorizer recognizes a VW ID model but cannot resolve the
*variant* (no trim alias matched the listing text), this asks Haiku to pick the most
valid variant using the model guide's "Variants & specs" knowledge together with the
offer's build year and description — exactly the "which trim was built when" judgement
a human would make.

Scoped to VW ID, gated by config + the global AI switch, non-destructive (only fills
an empty variant / battery, mirroring `apply_categorization`), and a no-op on
`model_locked` listings. With the agent off or no guide present, behaviour is the
deterministic categorizer's, unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from carcatcher.ai.client import AIClient, StructuredResult
from carcatcher.ai.models import HAIKU
from carcatcher.db.models import Listing
from carcatcher.normalization.guide_loader import GuideKnowledge
from carcatcher.normalization.model_categorizer import categorize

TOOL_NAME = "categorize_variant"

# Stable (cached) persona. The per-offer guide text + offer fields go in user_text so
# the cache stays warm across listings.
GUIDE_CATEGORIZER_SYSTEM = """\
You are a Volkswagen ID. (electric) variant expert for the German used-car market.
You are given an excerpt from a model guide listing the trims/variants that exist for
one VW ID model, which usable battery sizes (kWh) they have, and in which build years
("Baujahre") they were sold — including facelifts (e.g. "ab 01/2024"). You are also
given one used-car offer: its build year and free-text description.

Your job: choose the single most valid variant name for this offer.

Rules:
- Output ONLY via the provided tool.
- Pick a variant name EXACTLY as written in the guide (e.g. "Pro S", "GTX", "Pure").
- Use the build year to exclude trims that did not exist yet (a 2021 car cannot be a
  trim the guide says arrived in 2024).
- Cross-check description hints (power in kW/PS, 4MOTION/Allrad, usable kWh, range).
- battery_kwh: the usable capacity in kWh ONLY if the chosen variant + year map to a
  single capacity in the guide; otherwise null. Never invent a value.
- If the offer is genuinely ambiguous between trims, return variant=null with low
  confidence rather than guessing.
Be conservative and source your choice in the guide text only.
"""

GUIDE_CATEGORIZER_TOOL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "variant": {
            "type": ["string", "null"],
            "description": "Canonical variant name from the guide, or null if undeterminable.",
        },
        "battery_kwh": {
            "type": ["number", "null"],
            "description": "Usable battery capacity in kWh if the variant+year map unambiguously, else null.",
        },
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
    },
    "required": ["variant", "confidence"],
    "additionalProperties": False,
}


@dataclass
class AgentVariant:
    variant: str | None = None
    battery_kwh: float | None = None
    confidence: str | None = None


def is_ambiguous_vw_id(listing: Listing) -> bool:
    """True when the agent should be consulted: a recognized VW ID model with no
    resolved variant, not user-locked. Mirrors the deterministic detector so a guide
    call only happens where deterministic trim matching came up empty."""
    if listing.model_locked or listing.variant:
        return False
    result = categorize(
        listing.make,
        listing.model,
        listing.variant,
        listing.year,
        listing.battery_kwh,
        text=listing.raw_title,
    )
    return result.matched


def _build_user_text(listing: Listing, knowledge: GuideKnowledge) -> str:
    years = f" (Baujahre {knowledge.year_range})" if knowledge.year_range else ""
    desc = (listing.raw_text or "").strip()[:1500]
    return (
        f"GUIDE — {knowledge.make} {knowledge.model}{years}:\n"
        f"{knowledge.variants_section}\n\n"
        "OFFER:\n"
        f"- Baujahr (year): {listing.year if listing.year is not None else 'unbekannt'}\n"
        f"- Titel: {listing.raw_title}\n"
        f"- Leistung: {f'{listing.power_kw} kW' if listing.power_kw else 'unbekannt'}\n"
        f"- Akku kWh (falls bekannt): {listing.battery_kwh if listing.battery_kwh is not None else 'unbekannt'}\n"
        f"- Beschreibung: {desc or '(keine)'}\n\n"
        "Choose the single most valid variant for this offer."
    )


def _parse(data: dict) -> AgentVariant:
    raw_variant = data.get("variant")
    variant = raw_variant.strip() if isinstance(raw_variant, str) and raw_variant.strip() else None
    raw_battery = data.get("battery_kwh")
    battery = float(raw_battery) if isinstance(raw_battery, (int, float)) else None
    confidence = data.get("confidence") if isinstance(data.get("confidence"), str) else None
    return AgentVariant(variant=variant, battery_kwh=battery, confidence=confidence)


def apply_agent_variant(listing: Listing, result: AgentVariant) -> bool:
    """Apply the agent's choice in place, non-destructively. Returns True if changed."""
    if listing.model_locked:
        return False
    changed = False
    if result.variant and not listing.variant:
        listing.variant = result.variant
        changed = True
    if result.battery_kwh is not None and listing.battery_kwh is None:
        listing.battery_kwh = result.battery_kwh
        changed = True
    return changed


class GuideCategorizer:
    """Wraps an AI provider to resolve one ambiguous VW ID listing's variant."""

    def __init__(self, ai: AIClient) -> None:
        self._ai = ai

    @property
    def enabled(self) -> bool:
        return self._ai.enabled

    async def categorize(
        self, listing: Listing, knowledge: GuideKnowledge
    ) -> tuple[AgentVariant, StructuredResult]:
        result = await self._ai.extract_structured(
            model=HAIKU,
            cached_system=GUIDE_CATEGORIZER_SYSTEM,
            user_text=_build_user_text(listing, knowledge),
            tool_name=TOOL_NAME,
            tool_schema=GUIDE_CATEGORIZER_TOOL_SCHEMA,
            tool_description="Pick the most valid variant for this VW ID offer from the guide.",
        )
        return _parse(result.data), result
