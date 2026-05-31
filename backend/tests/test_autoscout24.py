"""AutoScout24 scraper tests against the committed real __NEXT_DATA__ fixture."""

from __future__ import annotations

from pathlib import Path

from carcatcher.scraping.autoscout24 import (
    AutoScout24Scraper,
    build_search_url,
    parse_search_html,
)
from carcatcher.schemas import StructuredFilters

FIXTURE = Path(__file__).parent / "fixtures" / "autoscout24_search.html"


def _html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parses_next_data_listings():
    stubs = parse_search_html(_html())
    assert len(stubs) == 3
    assert all(s.source == "autoscout24" for s in stubs)
    assert all(s.url.startswith("https://www.autoscout24.de/") for s in stubs)


def test_structured_specs_populated():
    stubs = parse_search_html(_html())
    scraper = AutoScout24Scraper(firecrawl=None)  # type: ignore[arg-type]
    specs = scraper.basic_specs(stubs[0])  # BMW X3
    assert specs["make"] == "BMW"
    assert specs["model"] == "X3"
    assert specs["price"] == 25000
    assert specs["mileage_km"] == 53063
    assert specs["year"] == 2024
    assert specs["fuel"] == "diesel"
    assert specs["transmission"] == "automatic"
    assert specs["power_kw"] == 140
    assert specs["seller_type"] == "dealer"
    assert specs["location_plz"] == "71154"


def test_scraper_is_structured_source():
    assert AutoScout24Scraper.provides_structured_data is True


def test_build_search_url():
    url = build_search_url(
        StructuredFilters(make="BMW", model="X3", price_max=30000, year_min=2020), page=2
    )
    assert url.startswith("https://www.autoscout24.de/lst/bmw/x3?")
    assert "page=2" in url
    assert "priceto=30000" in url
    assert "fregfrom=2020" in url


def test_parse_source_id_uuid():
    scraper = AutoScout24Scraper(firecrawl=None)  # type: ignore[arg-type]
    sid = scraper.parse_source_id(
        "https://www.autoscout24.de/angebote/bmw-x3-cat_883482c0-d08c-45f2-b997-abcd14487f9b"
    )
    assert sid == "883482c0-d08c-45f2-b997-abcd14487f9b"
