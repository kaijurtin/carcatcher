"""Extractor tests: schema mapping + enum coercion via a mocked AIClient."""

from __future__ import annotations

from carcatcher.ai.client import AIClient
from carcatcher.config import Settings
from carcatcher.normalization.extractor import Extractor
from tests.fakes import FakeAnthropic


def _extractor(tool_input: dict) -> Extractor:
    ai = AIClient(Settings(), client=FakeAnthropic(tool_input))
    return Extractor(ai)


async def test_maps_fields():
    ex = _extractor(
        {
            "make": "Volkswagen", "model": "Golf", "variant": "1.6",
            "fuel": "petrol", "transmission": "manual", "power_kw": 75,
            "year": 2005, "mileage_km": 112000, "price": 4300,
            "seller_type": "private", "location_plz": "39108",
        }
    )
    norm, result = await ex.extract("VW Golf 1.6", "TÜV neu, Benziner")
    assert norm.make == "Volkswagen"
    assert norm.fuel == "petrol"
    assert norm.power_kw == 75
    assert result.usage.input_tokens > 0


async def test_invalid_enum_coerced_to_none():
    ex = _extractor({"make": "BMW", "fuel": "kerosene", "transmission": "cvt"})
    norm, _ = await ex.extract("BMW", "weird")
    assert norm.make == "BMW"
    assert norm.fuel is None
    assert norm.transmission is None


async def test_missing_fields_are_null():
    ex = _extractor({"make": "Audi"})
    norm, _ = await ex.extract("Audi A4", "")
    assert norm.make == "Audi"
    assert norm.model is None
    assert norm.price is None
