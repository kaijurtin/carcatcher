"""VW.de parser tests against a trimmed real API response fixture."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from carcatcher.scraping.vwde import (
    VwDeError,
    VwDeParser,
    build_params,
    parse_search_response,
)

FIXTURE = Path(__file__).parent / "fixtures" / "vwde_search.json"
API_URL = "https://v3-120-0.gsl.feature-app.io/bff/car/search"


def _data() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parses_all_cars():
    listings = parse_search_response(_data(), "id4")
    assert len(listings) == 4
    assert all(l.source == "vw" for l in listings)
    assert all(l.model == "id4" for l in listings)


def test_fields_mapped_correctly():
    listings = parse_search_response(_data(), "id4")
    first = listings[0]
    assert first.source_id == "DEU4385118916-34"
    assert first.trim == "ID.4 Pure 2,49% WÄRMEPU NAV 5J-GAR MATRIX APP 19"
    assert first.price_eur == 34410
    assert first.mileage_km == 10937
    assert first.year == 2025
    assert first.power_kw == 125
    assert first.condition == "used"
    assert first.location == "Kölln-Reisiek"
    assert first.url == (
        "https://www.volkswagen.de/de/modelle/verfuegbare-fahrzeuge-suche.html"
        "/__app/search/car/REVVNDM4NTExODkxNi0zNA=.app"
    )


def test_new_car_condition_mapped():
    listings = parse_search_response(_data(), "id4")
    gtx = next(l for l in listings if l.source_id == "DEU12345000-01")
    assert gtx.condition == "new"


def test_unexpected_response_shape_raises():
    with pytest.raises(VwDeError):
        parse_search_response({"unexpected": True}, "id4")


def test_build_params_selects_model_code():
    assert build_params("id4", page=1)["t_model"] == "BQIE"
    assert build_params("id3", page=1)["t_model"] == "BQID"
    assert build_params("id4", page=1)["t_manuf"] == "BQ"


@respx.mock
def test_fetch_listings_paginates_using_page_max():
    page1 = _data()
    page1["meta"]["pageMax"] = 2
    page2 = {"meta": {"pageMax": 2}, "cars": []}
    respx.get(API_URL).mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
    )
    parser = VwDeParser()
    listings = parser.fetch_listings("id4")
    assert len(listings) == 4


def test_battery_kwh_parsed_from_subtitle_when_present():
    data = _data()
    data["cars"][0]["subtitle"]["value"] = "ID.4 Pro 77 kWh NAV"
    listings = parse_search_response(data, "id4")
    assert listings[0].battery_kwh == 77.0


def test_battery_kwh_is_none_when_no_kwh_mentioned():
    listings = parse_search_response(_data(), "id4")
    assert all(l.battery_kwh is None for l in listings)
