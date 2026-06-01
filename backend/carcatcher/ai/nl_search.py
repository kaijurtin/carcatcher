"""Natural-language search: free text -> structured filters + ranking + rationale."""

from __future__ import annotations

from carcatcher.ai.client import AIClient, StructuredResult
from carcatcher.ai.models import SONNET

TOOL_NAME = "build_search"

NL_SEARCH_SYSTEM = """\
You translate a German/English natural-language used-car request into structured
search filters plus a ranking. Be faithful to the request; leave anything unstated
as null. Output ONLY via the tool.

Filter rules:
- make: canonical manufacturer ("VW"->"Volkswagen", "Merc"/"MB"->"Mercedes-Benz").
- model: model line only ("Golf", "3er").
- fuel: petrol/diesel/hybrid/electric/lpg/cng (Benzin->petrol, Diesel->diesel,
  Elektro->electric, "sparsam"/economical -> prefer diesel or hybrid).
- transmission: manual/automatic (Automatik->automatic, Schaltung->manual).
- price_max / price_min in EUR; mileage_max in km; year_min/year_max are registration years.
- battery_kwh_min / battery_kwh_max: EV usable battery capacity in kWh ("mindestens 77 kWh"
  -> battery_kwh_min: 77). Only for electric/hybrid requests.
- battery_soh_min: EV battery State of Health floor in percent ("SoH ab 90%" -> 90).
- "Kombi"/estate, "Familienauto" -> hint via model/keywords, not a hard filter.
- plz: 5-digit German postal code if a location is given.

Ranking: order matters. Common intents:
- "günstig"/cheap/best deal -> rank by deal_score desc (best value first).
- "neuste"/low mileage -> mileage_km asc; "jung"/newest -> year desc.
Provide 1–3 ranking entries; field one of price, mileage_km, year, deal_score.

rationale: one short sentence explaining how you interpreted the request.
"""

NL_SEARCH_TOOL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "filters": {
            "type": "object",
            "properties": {
                "make": {"type": ["string", "null"]},
                "model": {"type": ["string", "null"]},
                "fuel": {"type": ["string", "null"]},
                "transmission": {"type": ["string", "null"]},
                "seller_type": {"type": ["string", "null"]},
                "year_min": {"type": ["integer", "null"]},
                "year_max": {"type": ["integer", "null"]},
                "price_min": {"type": ["integer", "null"]},
                "price_max": {"type": ["integer", "null"]},
                "mileage_max": {"type": ["integer", "null"]},
                "battery_kwh_min": {"type": ["integer", "null"]},
                "battery_kwh_max": {"type": ["integer", "null"]},
                "battery_soh_min": {"type": ["integer", "null"]},
                "plz": {"type": ["string", "null"]},
            },
        },
        "ranking": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "enum": ["price", "mileage_km", "year", "deal_score"]},
                    "direction": {"type": "string", "enum": ["asc", "desc"]},
                },
                "required": ["field", "direction"],
            },
        },
        "rationale": {"type": "string"},
    },
    "required": ["filters", "rationale"],
}


class Translator:
    def __init__(self, ai: AIClient) -> None:
        self._ai = ai

    @property
    def enabled(self) -> bool:
        return self._ai.enabled

    async def translate(self, query: str) -> tuple[dict, StructuredResult]:
        result = await self._ai.extract_structured(
            model=SONNET,
            cached_system=NL_SEARCH_SYSTEM,
            user_text=f"REQUEST: {query}",
            tool_name=TOOL_NAME,
            tool_schema=NL_SEARCH_TOOL_SCHEMA,
            tool_description="Build the structured search from the request.",
        )
        return result.data, result
