"""Tests for Nominatim geocoding and Haversine distance."""

from __future__ import annotations

import httpx
import pytest
import respx

from carcatcher.geocoding import NOMINATIM_URL, NominatimGeocoder, haversine_km


@respx.mock
def test_geocode_returns_lat_lon_from_first_result():
    respx.get(NOMINATIM_URL).mock(
        return_value=httpx.Response(200, json=[{"lat": "49.4465237", "lon": "6.6269649"}])
    )
    geocoder = NominatimGeocoder()
    assert geocoder.geocode("66663 Merzig") == (49.4465237, 6.6269649)


@respx.mock
def test_geocode_returns_none_for_no_results():
    respx.get(NOMINATIM_URL).mock(return_value=httpx.Response(200, json=[]))
    geocoder = NominatimGeocoder()
    assert geocoder.geocode("Nonexistent Place XYZ") is None


@respx.mock
def test_geocode_returns_none_on_http_error():
    respx.get(NOMINATIM_URL).mock(return_value=httpx.Response(500))
    geocoder = NominatimGeocoder()
    assert geocoder.geocode("Berlin") is None


@respx.mock
def test_geocode_returns_none_on_malformed_json():
    respx.get(NOMINATIM_URL).mock(return_value=httpx.Response(200, text="not json"))
    geocoder = NominatimGeocoder()
    assert geocoder.geocode("Berlin") is None


@respx.mock
def test_geocode_sends_a_descriptive_user_agent_and_germany_hint():
    route = respx.get(NOMINATIM_URL).mock(
        return_value=httpx.Response(200, json=[{"lat": "1", "lon": "2"}])
    )
    NominatimGeocoder().geocode("24941 Flensburg")
    request = route.calls.last.request
    assert "carcatcher" in request.headers["User-Agent"]
    assert request.url.params["q"] == "24941 Flensburg, Germany"


@respx.mock
def test_throttles_to_one_request_per_second(monkeypatch):
    respx.get(NOMINATIM_URL).mock(
        return_value=httpx.Response(200, json=[{"lat": "1", "lon": "2"}])
    )
    sleep_calls: list[float] = []
    times = iter([100.0, 100.2, 100.2])
    monkeypatch.setattr("carcatcher.geocoding.time.monotonic", lambda: next(times))
    monkeypatch.setattr("carcatcher.geocoding.time.sleep", lambda s: sleep_calls.append(s))

    geocoder = NominatimGeocoder()
    geocoder.geocode("A")
    geocoder.geocode("B")
    assert sleep_calls == [pytest.approx(0.8)]


def test_haversine_km_same_point_is_zero():
    assert haversine_km(49.44, 6.63, 49.44, 6.63) == 0.0


def test_haversine_km_berlin_to_munich():
    berlin = (52.5200, 13.4050)
    munich = (48.1351, 11.5820)
    assert haversine_km(*berlin, *munich) == pytest.approx(504.4, abs=1.0)
