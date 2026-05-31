"""Kleinanzeigen parser + URL builder tests against the committed real fixture."""

from __future__ import annotations

from pathlib import Path

from carcatcher.scraping.kleinanzeigen import (
    KleinanzeigenScraper,
    build_search_url,
    parse_card_specs,
    parse_search_html,
)
from carcatcher.schemas import StructuredFilters

FIXTURE = Path(__file__).parent / "fixtures" / "kleinanzeigen_search.html"


def _html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parse_search_skips_gesuch_and_returns_sales():
    stubs = parse_search_html(_html())
    # Fixture has 1 Gesuch (wanted ad) + 3 sales; Gesuch must be excluded.
    assert len(stubs) == 3
    assert all("Gesuch" not in t for s in stubs for t in s.tags)


def test_stub_fields_populated():
    stubs = parse_search_html(_html())
    s = stubs[0]
    assert s.source == "kleinanzeigen"
    assert s.source_id.isdigit()
    assert s.url.startswith("https://www.kleinanzeigen.de/")
    assert s.title
    assert s.price_hint and "€" in s.price_hint


def test_parse_card_specs_extracts_price_mileage_year():
    specs = parse_card_specs("7.800 € VB", ["193.000 km", "EZ 03/2013"])
    assert specs["price"] == 7800
    assert specs["price_negotiable"] is True
    assert specs["mileage_km"] == 193000
    assert specs["year"] == 2013


def test_parse_card_specs_fixed_price_not_negotiable():
    specs = parse_card_specs("999 €", ["0 km", "EZ 05/2013"])
    assert specs["price"] == 999
    assert specs["price_negotiable"] is False


def test_build_search_url_contains_segments():
    url = build_search_url(
        StructuredFilters(make="VW", model="Golf", price_min=1000, price_max=5000),
        page=2,
    )
    assert url.startswith("https://www.kleinanzeigen.de/s-autos/")
    assert "seite:2" in url
    assert "vw-golf" in url
    assert "preis:1000:5000" in url
    assert url.endswith("/c216")


def test_parse_source_id_from_url():
    scraper = KleinanzeigenScraper(firecrawl=None)  # type: ignore[arg-type]
    sid = scraper.parse_source_id(
        "https://www.kleinanzeigen.de/s-anzeige/vw-golf/3400302623-216-2229"
    )
    assert sid == "3400302623"


def test_basic_specs_via_scraper():
    stubs = parse_search_html(_html())
    scraper = KleinanzeigenScraper(firecrawl=None)  # type: ignore[arg-type]
    # At least one sale stub should yield a numeric price.
    prices = [scraper.basic_specs(s).get("price") for s in stubs]
    assert any(p for p in prices)
