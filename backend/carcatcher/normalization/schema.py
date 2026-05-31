"""Normalized listing schema (Haiku output) + the tool input schema it must match.

The model never fabricates: anything not stated in the listing stays null. Enum
fields coerce unknown values to None so a bad guess can't pollute scoring.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator

FUELS = {"petrol", "diesel", "hybrid", "electric", "lpg", "cng", "other"}
TRANSMISSIONS = {"manual", "automatic"}
SELLER_TYPES = {"private", "dealer"}


class NormalizedListing(BaseModel):
    price: int | None = None
    price_negotiable: bool = False
    mileage_km: int | None = None
    year: int | None = None
    make: str | None = None
    model: str | None = None
    variant: str | None = None
    fuel: str | None = None
    transmission: str | None = None
    power_kw: int | None = None
    body_type: str | None = None
    location_city: str | None = None
    location_plz: str | None = None
    seller_type: str | None = None

    @field_validator("fuel")
    @classmethod
    def _v_fuel(cls, v: str | None) -> str | None:
        return v if v in FUELS else None

    @field_validator("transmission")
    @classmethod
    def _v_trans(cls, v: str | None) -> str | None:
        return v if v in TRANSMISSIONS else None

    @field_validator("seller_type")
    @classmethod
    def _v_seller(cls, v: str | None) -> str | None:
        return v if v in SELLER_TYPES else None


def _str() -> dict:
    return {"type": ["string", "null"]}


def _int() -> dict:
    return {"type": ["integer", "null"]}


# Self-contained JSON schema (no $ref) for the Anthropic tool input.
NORMALIZED_TOOL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "price": {**_int(), "description": "Asking price in EUR, digits only"},
        "price_negotiable": {"type": "boolean", "description": "true if VB/Verhandlungsbasis"},
        "mileage_km": _int(),
        "year": {**_int(), "description": "Year of first registration (Erstzulassung)"},
        "make": {**_str(), "description": "Canonical manufacturer, e.g. Volkswagen"},
        "model": _str(),
        "variant": {**_str(), "description": "Trim/engine variant, e.g. 1.5 TSI Comfortline"},
        "fuel": {"type": ["string", "null"], "enum": [*sorted(FUELS), None]},
        "transmission": {"type": ["string", "null"], "enum": [*sorted(TRANSMISSIONS), None]},
        "power_kw": {**_int(), "description": "Engine power in kW (convert from PS: kW≈PS*0.7355)"},
        "body_type": _str(),
        "location_city": _str(),
        "location_plz": {**_str(), "description": "German postal code (PLZ)"},
        "seller_type": {"type": ["string", "null"], "enum": [*sorted(SELLER_TYPES), None]},
    },
    "required": [],
}
