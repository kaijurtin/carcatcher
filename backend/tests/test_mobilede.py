"""mobile.de scraper tests against a representative JSON-LD fixture.

NOTE: the fixture mirrors schema.org Car JSON-LD; validate against a live Firecrawl
fetch on first deploy (mobile.de is DataDome-protected and could not be sampled).
"""

from __future__ import annotations

from pathlib import Path

from carcatcher.scraping.mobilede import (
    MobileDeScraper,
    build_search_url,
    parse_search_html,
)
from carcatcher.schemas import StructuredFilters

FIXTURE = Path(__file__).parent / "fixtures" / "mobilede_search.html"


def _html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parses_jsonld_vehicles():
    stubs = parse_search_html(_html())
    assert len(stubs) == 2
    assert {s.source for s in stubs} == {"mobilede"}
    assert {s.source_id for s in stubs} == {"411111111", "422222222"}


def test_basic_specs_from_jsonld():
    stubs = parse_search_html(_html())
    scraper = MobileDeScraper(firecrawl=None)  # type: ignore[arg-type]
    golf = next(s for s in stubs if s.source_id == "411111111")
    specs = scraper.basic_specs(golf)
    assert specs["make"] == "Volkswagen"
    assert specs["model"] == "Golf"
    assert specs["price"] == 12990
    assert specs["mileage_km"] == 118000
    assert specs["year"] == 2016
    assert specs["fuel"] == "diesel"
    assert specs["transmission"] == "manual"
    assert specs["seller_type"] == "dealer"
    assert specs["location_plz"] == "80331"


def test_private_seller_detected():
    stubs = parse_search_html(_html())
    scraper = MobileDeScraper(firecrawl=None)  # type: ignore[arg-type]
    bmw = next(s for s in stubs if s.source_id == "422222222")
    assert scraper.basic_specs(bmw)["seller_type"] == "private"
    assert scraper.basic_specs(bmw)["transmission"] == "automatic"


def test_not_structured_source():
    # JSON-LD may be partial → Haiku still supplements.
    assert MobileDeScraper.provides_structured_data is False


def test_build_search_url():
    url = build_search_url(StructuredFilters(price_max=15000), page=3)
    assert url.startswith("https://suchen.mobile.de/fahrzeuge/search.html?")
    assert "pageNumber=3" in url
    assert "price:to=15000" in url
