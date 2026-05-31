"""mobile.de scraper (source: "mobilede").

mobile.de is behind DataDome, so in production the page is fetched + rendered by
Firecrawl. We parse schema.org JSON-LD (Car/Vehicle items, optionally wrapped in an
ItemList) — a stable, standards-based structure. Haiku still runs to fill any gaps
from the description (non-destructive).

NOTE: the exact JSON-LD payload should be validated against a live Firecrawl fetch
on first deploy; parsing is isolated here for a one-file fix if the shape differs.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator

from bs4 import BeautifulSoup

from carcatcher.scraping.base import ListingStub, RawPage, Scraper
from carcatcher.scraping.firecrawl_client import FirecrawlClient
from carcatcher.schemas import StructuredFilters

logger = logging.getLogger(__name__)

SOURCE = "mobilede"
BASE_URL = "https://suchen.mobile.de"

_ID_RE = re.compile(r"[?&]id=(\d+)")
_VEHICLE_TYPES = {"Car", "Vehicle", "Product", "MotorizedVehicle"}

_FUEL_MAP = {
    "benzin": "petrol", "petrol": "petrol", "diesel": "diesel",
    "elektro": "electric", "electric": "electric", "hybrid": "hybrid",
    "autogas": "lpg", "lpg": "lpg", "erdgas": "cng", "cng": "cng",
}
_TRANSMISSION_MAP = {
    "manuell": "manual", "schaltgetriebe": "manual", "manual": "manual",
    "automatik": "automatic", "automatic": "automatic",
}


def _map(table: dict, value) -> str | None:
    return table.get(str(value).strip().lower()) if value else None


def _to_int(value) -> int | None:
    if value is None:
        return None
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def _iter_vehicles(node) -> list[dict]:
    """Collect Car/Vehicle dicts from arbitrary JSON-LD (handles ItemList)."""
    found: list[dict] = []

    def visit(o):
        if isinstance(o, dict):
            t = o.get("@type")
            types = t if isinstance(t, list) else [t]
            if any(x in _VEHICLE_TYPES for x in types):
                found.append(o)
            for v in o.values():
                visit(v)
        elif isinstance(o, list):
            for v in o:
                visit(v)

    visit(node)
    return found


def _vehicle_to_stub(item: dict) -> ListingStub | None:
    url = item.get("url") or item.get("@id") or ""
    if not url:
        return None
    m = _ID_RE.search(url)
    source_id = m.group(1) if m else url.rstrip("/").rsplit("/", 1)[-1]

    offers = item.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    place = (offers.get("availableAtOrFrom") or {}) if isinstance(offers, dict) else {}
    address = place.get("address") or {} if isinstance(place, dict) else {}
    seller = offers.get("seller") or {} if isinstance(offers, dict) else {}
    seller_type = (
        "dealer" if str(seller.get("@type", "")).lower() in {"autodealer", "organization"}
        else "private" if str(seller.get("@type", "")).lower() == "person"
        else None
    )
    odo = item.get("mileageFromOdometer") or {}
    mileage = _to_int(odo.get("value") if isinstance(odo, dict) else odo)
    brand = item.get("brand") or {}
    make = brand.get("name") if isinstance(brand, dict) else brand
    price = _to_int(offers.get("price") if isinstance(offers, dict) else None)
    image = item.get("image")
    if isinstance(image, list):
        image = image[0] if image else None

    stub = ListingStub(
        source=SOURCE,
        source_id=str(source_id),
        url=url,
        title=item.get("name") or f"{make or ''} {item.get('model') or ''}".strip(),
        price_hint=f"{price} €" if price else None,
        location_hint=" ".join(
            p for p in (address.get("postalCode"), address.get("addressLocality")) if p
        ) or None,
        image_hint=image,
        tags=[t for t in (
            f"{mileage} km" if mileage else None,
            f"EZ {item.get('vehicleModelDate')}" if item.get("vehicleModelDate") else None,
            item.get("fuelType"),
        ) if t],
        description_hint=item.get("description") or item.get("name"),
    )
    stub._mde = {  # type: ignore[attr-defined]
        "price": price,
        "make": make,
        "model": item.get("model"),
        "mileage_km": mileage,
        "year": _to_int(item.get("vehicleModelDate")),
        "fuel": _map(_FUEL_MAP, item.get("fuelType")),
        "transmission": _map(_TRANSMISSION_MAP, item.get("vehicleTransmission")),
        "seller_type": seller_type,
        "location_city": address.get("addressLocality"),
        "location_plz": address.get("postalCode"),
    }
    return stub


def parse_search_html(html: str) -> list[ListingStub]:
    soup = BeautifulSoup(html, "html.parser")
    stubs: list[ListingStub] = []
    seen: set[str] = set()
    for node in soup.find_all("script", type="application/ld+json"):
        if not node.string:
            continue
        try:
            data = json.loads(node.string)
        except json.JSONDecodeError:
            continue
        for vehicle in _iter_vehicles(data):
            stub = _vehicle_to_stub(vehicle)
            if stub and stub.source_id not in seen:
                seen.add(stub.source_id)
                stubs.append(stub)
    return stubs


def build_search_url(filters: StructuredFilters, page: int = 1) -> str:
    params = [("isSearchRequest", "true"), ("s", "Car"), ("vc", "Car"), ("pageNumber", str(page))]
    if filters.price_min is not None:
        params.append(("price:from", str(filters.price_min)))
    if filters.price_max is not None:
        params.append(("price:to", str(filters.price_max)))
    if filters.mileage_max is not None:
        params.append(("mileage:to", str(filters.mileage_max)))
    if filters.year_min is not None:
        params.append(("firstRegistration:from", str(filters.year_min)))
    query = "&".join(f"{k}={v}" for k, v in params)
    return f"{BASE_URL}/fahrzeuge/search.html?{query}"


class MobileDeScraper(Scraper):
    name = SOURCE
    base_url = BASE_URL
    provides_structured_data = False  # JSON-LD may be partial; let Haiku supplement

    def __init__(self, firecrawl: FirecrawlClient) -> None:
        self._fc = firecrawl

    async def search(
        self, filters: StructuredFilters, *, max_pages: int
    ) -> AsyncIterator[ListingStub]:
        for page in range(1, max_pages + 1):
            url = build_search_url(filters, page)
            try:
                data = await self._fc.scrape(
                    url, formats=["rawHtml"], only_main_content=False
                )
            except Exception as exc:  # noqa: BLE001 — transient page error shouldn't fail the run
                logger.warning("mobilede page %s failed, stopping paging: %s", page, exc)
                break
            html = data.get("rawHtml") or data.get("html") or ""
            stubs = parse_search_html(html)
            if not stubs:
                break
            for stub in stubs:
                yield stub

    async def fetch_detail(self, url: str) -> RawPage:
        data = await self._fc.scrape(url, formats=["markdown", "html"])
        return RawPage(url=url, markdown=data.get("markdown", ""), html=data.get("html"))

    def parse_source_id(self, url: str) -> str:
        m = _ID_RE.search(url)
        return m.group(1) if m else url.rstrip("/").rsplit("/", 1)[-1]

    def basic_specs(self, stub: ListingStub) -> dict:
        specs = getattr(stub, "_mde", {})
        return {k: v for k, v in specs.items() if v is not None}
