"""mobile.de scraper tests against a window.__INITIAL_STATE__ fixture.

mobile.de exposes search results in window.__INITIAL_STATE__ (no vehicle JSON-LD).
The fixture mirrors the real shape at search.srp.data.searchResults.items.
"""

from __future__ import annotations

from pathlib import Path

from carcatcher.scraping.mobilede import (
    MobileDeScraper,
    build_search_url,
    extract_initial_state,
    parse_search_html,
)
from carcatcher.schemas import StructuredFilters

FIXTURE = Path(__file__).parent / "fixtures" / "mobilede_search.html"


def _html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_extract_initial_state_brace_matches():
    state = extract_initial_state(_html())
    assert state is not None
    assert state.startswith("{") and state.endswith("}")
    assert '"__OTHER__"' not in state  # stops at the matching brace, ignores trailing


def test_parses_initial_state_vehicles_and_skips_eyecatcher():
    stubs = parse_search_html(_html())
    assert {s.source for s in stubs} == {"mobilede"}
    # The isEyeCatcher ad (499999999) is excluded.
    assert {s.source_id for s in stubs} == {"411111111", "422222222"}


def test_basic_specs_dealer_diesel():
    stubs = parse_search_html(_html())
    scraper = MobileDeScraper(firecrawl=None)  # type: ignore[arg-type]
    golf = next(s for s in stubs if s.source_id == "411111111")
    specs = scraper.basic_specs(golf)
    assert specs["make"] == "Volkswagen"
    assert specs["model"] == "Golf"
    assert specs["price"] == 12990
    assert specs["mileage_km"] == 118000
    assert specs["year"] == 2016
    assert specs["power_kw"] == 110
    assert specs["fuel"] == "diesel"
    assert specs["transmission"] == "manual"
    assert specs["seller_type"] == "dealer"
    assert specs["location_plz"] == "80331"
    assert golf.url == "https://suchen.mobile.de/fahrzeuge/details.html?id=411111111&ref=srp&s=Car"


def test_basic_specs_private_electric():
    stubs = parse_search_html(_html())
    scraper = MobileDeScraper(firecrawl=None)  # type: ignore[arg-type]
    bmw = next(s for s in stubs if s.source_id == "422222222")
    specs = scraper.basic_specs(bmw)
    assert specs["seller_type"] == "private"
    assert specs["transmission"] == "automatic"
    assert specs["fuel"] == "electric"
    assert specs["power_kw"] == 250
    assert specs["year"] == 2022


def test_parse_source_id_from_url():
    scraper = MobileDeScraper(firecrawl=None)  # type: ignore[arg-type]
    assert scraper.parse_source_id(
        "https://suchen.mobile.de/fahrzeuge/details.html?id=455109968&s=Car"
    ) == "455109968"


def test_not_structured_source():
    # The agent decides make/model/variant from the announcement text.
    assert MobileDeScraper.provides_structured_data is False


def test_build_search_url_paging_and_price():
    url = build_search_url(StructuredFilters(price_max=15000), page=3)
    assert url.startswith("https://suchen.mobile.de/fahrzeuge/search.html?")
    assert "pageNumber=3" in url
    assert "price:to=15000" in url


def test_build_search_url_make_targeting():
    # make name and its alias both resolve to the verified makeId.
    assert "ms=25200" in build_search_url(StructuredFilters(make="Volkswagen"))
    assert "ms=25200" in build_search_url(StructuredFilters(make="VW"))
    assert "ms=17200" in build_search_url(StructuredFilters(make="Mercedes-Benz"))
    # unknown make -> no ms param (broad crawl; Phase-A filter narrows later)
    assert "ms=" not in build_search_url(StructuredFilters(make="Wuling"))
