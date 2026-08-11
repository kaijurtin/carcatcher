"""AutoScout24 parser tests against the committed real __NEXT_DATA__ fixture."""

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
    bmw = listings[0]
    assert bmw.trim == "xDrive20d Aut. Mild-Hybrid"
    assert bmw.price_eur == 25000
    assert bmw.mileage_km == 53063
    assert bmw.year == 2024
    assert bmw.power_kw == 140
    assert bmw.condition == "used"
    assert bmw.location == "71154 Nufringen"
    assert bmw.source_id == "883482c0-d08c-45f2-b997-abcd14487f9b"


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
