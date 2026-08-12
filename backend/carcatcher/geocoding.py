"""Geocoding via the free Nominatim (OpenStreetMap) API, plus great-circle
distance. Geocoding failures never raise — a listing simply keeps null
coordinates rather than failing the crawl that's fetching it."""

from __future__ import annotations

import logging
import time
from math import asin, cos, radians, sin, sqrt
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "carcatcher/0.1 (personal used-car tracker; github.com/kaijurtin/carcatcher)"
MIN_REQUEST_INTERVAL_SECONDS = 1.0  # Nominatim usage policy cap: 1 request/second
_EARTH_RADIUS_KM = 6371.0


class Geocoder(Protocol):
    def geocode(self, location: str) -> tuple[float, float] | None: ...


class NominatimGeocoder:
    """Looks up (latitude, longitude) for a free-text German location string
    (e.g. "24941 Flensburg" or "Kölln-Reisiek") via Nominatim. Self-throttles
    to Nominatim's 1 request/second usage-policy cap."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=10.0, headers={"User-Agent": USER_AGENT})
        self._last_request_at: float | None = None

    def geocode(self, location: str) -> tuple[float, float] | None:
        self._throttle()
        try:
            resp = self._client.get(
                NOMINATIM_URL, params={"q": f"{location}, Germany", "format": "json", "limit": 1}
            )
            resp.raise_for_status()
            results = resp.json()
        except (httpx.HTTPError, ValueError):
            logger.warning("geocoding failed for location=%r", location, exc_info=True)
            return None
        finally:
            self._last_request_at = time.monotonic()
        if not results:
            return None
        try:
            return float(results[0]["lat"]), float(results[0]["lon"])
        except (KeyError, TypeError, ValueError):
            return None

    def _throttle(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in kilometers."""
    rlat1, rlon1, rlat2, rlon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = rlat2 - rlat1, rlon2 - rlon1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * asin(sqrt(a))
