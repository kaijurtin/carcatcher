"""VW.de parser (source: "vw").

Volkswagen's own official used/new-car search. The public search page
(volkswagen.de/.../verfuegbare-fahrzeuge-suche.html) is a client-hydrated React app
with no listing data in its initial HTML; the actual data comes from a JSON API the
page calls, verified live 2026-08-11 to work over plain HTTP with no browser and no
session/cookies required (a fresh, cookie-less request succeeds).
"""

from __future__ import annotations

import re

import httpx

from carcatcher.scraping.base import Model, Parser, RawListing

SOURCE = "vw"
API_URL = "https://v3-120-0.gsl.feature-app.io/bff/car/search"
DETAIL_URL = (
    "https://www.volkswagen.de/de/modelle/verfuegbare-fahrzeuge-suche.html"
    "/__app/search/car/{key}.app"
)

_MODEL_CODES: dict[Model, str] = {"id3": "BQID", "id4": "BQIE"}

# Static per-deploy credentials for VW's onehub_pkw "publish" feature-app config,
# verified live 2026-08-11 to work from a fresh, cookie-less request (not
# session-bound). If VW redeploys and rotates `dataVersion`, calls will start
# failing loudly (see `parse_search_response`) rather than silently returning
# nothing — that's the signal a credential refresh is needed.
_STATIC_PARAMS = {
    "country": "DE",
    "language": "de",
    "market": "passenger",
    "oneapiKey": "nOqkwPxxu8ViK9aaHvTkglzVZAlX4yIx",
    "dataVersion": "B62F538267A27D9C9B1AC0E02FF3688F",
    "endpoint": (
        '{"endpoint":{"type":"publish","country":"de","language":"de",'
        '"content":"onehub_pkw","envName":"prod","testScenarioId":null},'
        '"signature":"eXxF3Vp4siIxU67pK2Vs14eGqdMbD0HzeFcn3b058j8="}'
    ),
}

_POWER_RE = re.compile(r"(\d+)\s*kW")
_YEAR_RE = re.compile(r"(\d{4})")


class VwDeError(RuntimeError):
    """Raised when VW's API responds with an unexpected shape (e.g. rotated credentials)."""


def _power_kw(label: str | None) -> int | None:
    if not label:
        return None
    m = _POWER_RE.search(label)
    return int(m.group(1)) if m else None


def _condition(car: dict) -> str:
    code = (car.get("cartype") or {}).get("code")
    return "new" if code == "N" else "used"


def _car_to_listing(car: dict, model: Model) -> RawListing | None:
    carid = car.get("carid")
    key = car.get("key")
    if not carid or not key:
        return None
    price = (car.get("parsedPrice") or {}).get("value")
    mileage = (car.get("mileage") or {}).get("raw_value")
    year_match = _YEAR_RE.match(car.get("initialreg") or "")
    dealer_city = ((car.get("dealer") or {}).get("city") or {}).get("value")
    return RawListing(
        source=SOURCE,
        source_id=str(carid),
        url=DETAIL_URL.format(key=key),
        model=model,
        trim=(car.get("subtitle") or {}).get("value") or car.get("title") or "",
        price_eur=int(price) if price is not None else None,
        mileage_km=int(mileage) if mileage is not None else None,
        year=int(year_match.group(1)) if year_match else None,
        power_kw=_power_kw(car.get("powerLabel")),
        condition=_condition(car),
        location=dealer_city,
        title=car.get("title") or "",
    )


def parse_search_response(data: dict, model: Model) -> list[RawListing]:
    if "cars" not in data or "meta" not in data:
        raise VwDeError(f"unexpected VW search response shape: keys={list(data.keys())}")
    cars = data.get("cars") or []
    out = [_car_to_listing(car, model) for car in cars]
    return [l for l in out if l is not None]


def build_params(model: Model, page: int) -> dict:
    return {
        **_STATIC_PARAMS,
        "t_manuf": "BQ",
        "t_model": _MODEL_CODES[model],
        "sort": "DATE_OFFER",
        "sortdirection": "DESC",
        "pageitems": 12,
        "page": page,
    }


class VwDeParser(Parser):
    name = SOURCE

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=20.0)

    def fetch_listings(self, model: Model) -> list[RawListing]:
        results: list[RawListing] = []
        page = 1
        page_max = 1
        while page <= page_max:
            resp = self._client.get(API_URL, params=build_params(model, page))
            resp.raise_for_status()
            data = resp.json()
            results.extend(parse_search_response(data, model))
            page_max = (data.get("meta") or {}).get("pageMax", page)
            page += 1
        return results
