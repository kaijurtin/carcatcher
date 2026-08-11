"""AutoScout24 parser tests against the committed real __NEXT_DATA__ fixture.

The fixture (`fixtures/autoscout24_search.html`) contains 3 real Volkswagen ID.4
listings (captured live from a properly URL-filtered /lst/volkswagen/id-4 search)
plus 1 deliberately-kept off-model BMW X3 entry — a regression case proving AS24
can return non-matching vehicles in unfiltered/sponsored slots even for a
model-specific search URL, and that the parser must guard against storing them.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import respx

from carcatcher.scraping.autoscout24 import (
    AutoScout24Parser,
    build_search_url,
    parse_search_html,
)

FIXTURE = Path(__file__).parent / "fixtures" / "autoscout24_search.html"


def _html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parses_next_data_listings():
    listings = parse_search_html(_html(), "id4")
    assert len(listings) == 3
    assert all(l.source == "autoscout24" for l in listings)
    assert all(l.model == "id4" for l in listings)
    assert all(l.url.startswith("https://www.autoscout24.de/") for l in listings)


def test_structured_fields_populated():
    listings = parse_search_html(_html(), "id4")
    first = listings[0]
    assert first.trim == "Pure Performance LED+ACC+APP-CONNECT+DAB+"
    assert first.price_eur == 25980
    assert first.mileage_km == 23584
    assert first.year == 2024
    assert first.power_kw == 125
    assert first.condition == "used"
    assert first.location == "24941 Flensburg"
    assert first.source_id == "7db4c4a2-5c22-42e2-8ecc-6f1ce5242d6d"


def test_excludes_off_model_bmw_x3_listing():
    """AS24 can return off-model vehicles in unfiltered/sponsored slots — the
    fixture's BMW X3 entry must be filtered out, not stored as a VW ID.4."""
    listings = parse_search_html(_html(), "id4")
    assert not any("X3" in l.trim for l in listings)
    assert not any("BMW" in l.title for l in listings)
    assert not any(l.source_id == "883482c0-d08c-45f2-b997-abcd14487f9b" for l in listings)


def test_returns_empty_list_for_html_without_next_data():
    assert parse_search_html("<html><body>no data here</body></html>", "id4") == []


def test_build_search_url_id4():
    url = build_search_url("id4", page=2)
    assert url == (
        "https://www.autoscout24.de/lst/volkswagen/id-4"
        "?atype=C&cy=D&sort=standard&desc=0&page=2&size=20"
    )


def test_build_search_url_id3():
    url = build_search_url("id3", page=1)
    assert "/lst/volkswagen/id-3?" in url


@respx.mock
def test_fetch_listings_paginates_until_an_empty_page():
    respx.get(build_search_url("id4", 1)).mock(return_value=httpx.Response(200, text=_html()))
    respx.get(build_search_url("id4", 2)).mock(
        return_value=httpx.Response(200, text="<html></html>")
    )
    parser = AutoScout24Parser()
    listings = parser.fetch_listings("id4")
    assert len(listings) == 3
