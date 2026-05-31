"""Sonnet per-listing evaluation: pros/cons/red-flags/verdict."""

from __future__ import annotations

from carcatcher.ai.client import AIClient, StructuredResult
from carcatcher.ai.models import SONNET
from carcatcher.ai.prompts import EVALUATION_SYSTEM
from carcatcher.db.models import Listing

TOOL_NAME = "record_evaluation"

EVALUATION_TOOL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "1–2 actionable sentences"},
        "pros": {"type": "array", "items": {"type": "string"}},
        "cons": {"type": "array", "items": {"type": "string"}},
        "red_flags": {"type": "array", "items": {"type": "string"}},
        "deal_verdict": {"type": "string", "enum": ["good", "fair", "overpriced"]},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["summary", "deal_verdict", "confidence"],
}


def _eur(value: int | None) -> str:
    return f"{value:,} EUR".replace(",", ".") if value is not None else "unknown"


def build_eval_input(listing: Listing) -> str:
    specs = [
        f"Make/Model: {listing.make or '?'} {listing.model or ''} {listing.variant or ''}".strip(),
        f"Year (EZ): {listing.year or '?'}",
        f"Mileage: {listing.mileage_km or '?'} km",
        f"Fuel: {listing.fuel or '?'} | Transmission: {listing.transmission or '?'}"
        f" | Power: {listing.power_kw or '?'} kW",
        f"Seller: {listing.seller_type or '?'} | Location: {listing.location_raw or '?'}",
        f"Asking price: {_eur(listing.price)}"
        + (" (negotiable)" if listing.price_negotiable else ""),
        f"Statistical fair price estimate: {_eur(listing.fair_price_estimate)}"
        + (f" (from {listing.comp_count} comparables)" if listing.comp_count else ""),
    ]
    desc = listing.raw_text.strip() or "(no description)"
    return "LISTING\n" + "\n".join(specs) + f"\n\nDESCRIPTION:\n{desc[:4000]}"


class Evaluator:
    def __init__(self, ai: AIClient) -> None:
        self._ai = ai

    @property
    def enabled(self) -> bool:
        return self._ai.enabled

    async def evaluate(self, listing: Listing) -> tuple[dict, StructuredResult]:
        result = await self._ai.extract_structured(
            model=SONNET,
            cached_system=EVALUATION_SYSTEM,
            user_text=build_eval_input(listing),
            tool_name=TOOL_NAME,
            tool_schema=EVALUATION_TOOL_SCHEMA,
            tool_description="Record your evaluation of this used-car listing.",
        )
        return result.data, result
