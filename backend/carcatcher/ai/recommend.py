"""Opus cross-candidate recommendation: 'buy THIS one because…' over a shortlist."""

from __future__ import annotations

from carcatcher.ai.client import AIClient, StructuredResult
from carcatcher.ai.models import OPUS
from carcatcher.db.models import Listing

TOOL_NAME = "record_recommendation"

RECOMMEND_SYSTEM = """\
You are a trusted advisor helping a private buyer choose between a shortlist of used
cars on the German market. Weigh price vs. the statistical fair-price estimate, the
per-listing evaluation (verdict, red flags), mileage-for-age, and overall value/risk.

Pick ONE car to recommend and explain why, concretely and honestly. Rank the rest.
Surface real caveats (e.g. "the cheapest is cheapest because of accident wording").
Refer to cars by their id. Output ONLY via the tool. Do not invent specs.
"""

RECOMMEND_TOOL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "top_pick_id": {"type": "integer", "description": "id of the recommended car"},
        "summary": {"type": "string", "description": "why the top pick wins, 2–4 sentences"},
        "ranking": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "listing_id": {"type": "integer"},
                    "rank": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["listing_id", "rank", "reason"],
            },
        },
        "caveats": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["top_pick_id", "summary", "ranking"],
}


def _car_block(listing: Listing) -> str:
    ev = listing.ai_evaluation or {}
    verdict = ev.get("deal_verdict", "not evaluated")
    ev_summary = ev.get("summary", "")
    flags = ", ".join(ev.get("red_flags", []) or []) or "none noted"
    fair = listing.fair_price_estimate
    deal = f"{round(listing.deal_score * 100)}% vs fair" if listing.deal_score is not None else "n/a"
    return (
        f"[id={listing.id}] {listing.make or '?'} {listing.model or ''} "
        f"{listing.variant or ''} | {listing.year or '?'} | "
        f"{listing.mileage_km or '?'} km | price {listing.price or '?'} EUR | "
        f"fair {fair or '?'} EUR ({deal}) | verdict: {verdict} | "
        f"red flags: {flags} | {ev_summary}"
    ).strip()


def build_recommend_input(listings: list[Listing]) -> str:
    return "SHORTLIST:\n" + "\n".join(_car_block(li) for li in listings)


class Recommender:
    def __init__(self, ai: AIClient) -> None:
        self._ai = ai

    @property
    def enabled(self) -> bool:
        return self._ai.enabled

    async def recommend(self, listings: list[Listing]) -> tuple[dict, StructuredResult]:
        result = await self._ai.extract_structured(
            model=OPUS,
            cached_system=RECOMMEND_SYSTEM,
            user_text=build_recommend_input(listings),
            tool_name=TOOL_NAME,
            tool_schema=RECOMMEND_TOOL_SCHEMA,
            tool_description="Record your shortlist recommendation.",
            max_tokens=2048,
        )
        return result.data, result
