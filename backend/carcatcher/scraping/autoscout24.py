"""AutoScout24.de scraper (source: "autoscout24").

AS24 is a Next.js app: the search results are in the __NEXT_DATA__ JSON
(props.pageProps.listings) with structured fields. We parse that JSON rather than the
DOM (robust) and use it as a seed via basic_specs; the agent (P2) still decides
make/model/variant from the announcement text so the model facet stays agent-decided.
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

SOURCE = "autoscout24"
BASE_URL = "https://www.autoscout24.de"

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_DIGITS_RE = re.compile(r"\d[\d.]*")
_UUID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")

_FUEL_MAP = {
    "benzin": "petrol", "diesel": "diesel", "elektro": "electric",
    "hybrid": "hybrid", "autogas (lpg)": "lpg", "lpg": "lpg",
    "erdgas (cng)": "cng", "cng": "cng",
}
_TRANSMISSION_MAP = {
    "automatik": "automatic", "schaltgetriebe": "manual",
    "halbautomatik": "automatic", "manuell": "manual",
}


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower().strip()).strip("-")


def _to_int(text: str | None) -> int | None:
    if not text:
        return None
    m = _DIGITS_RE.search(text)
    if not m:
        return None
    digits = m.group(0).replace(".", "")
    return int(digits) if digits.isdigit() else None


def _map_fuel(text: str | None) -> str | None:
    return _FUEL_MAP.get((text or "").strip().lower())


def _map_transmission(text: str | None) -> str | None:
    return _TRANSMISSION_MAP.get((text or "").strip().lower())


def _parse_power_kw(text: str | None) -> int | None:
    # "140 kW (190 PS)" -> 140
    if not text:
        return None
    m = re.search(r"(\d+)\s*kW", text)
    return int(m.group(1)) if m else None


def _year_from_calendar(text: str | None) -> int | None:
    # "02/2024" -> 2024
    if not text:
        return None
    m = re.search(r"(\d{4})", text)
    return int(m.group(1)) if m else None


def _details_map(vehicle_details: list) -> dict:
    """Map AS24 vehicleDetails (icon/data pairs) to our fields."""
    out: dict = {}
    for d in vehicle_details or []:
        icon, value = d.get("iconName"), d.get("data")
        if icon == "mileage_odometer":
            out["mileage_km"] = _to_int(value)
        elif icon == "calendar":
            out["year"] = _year_from_calendar(value)
        elif icon == "speedometer":
            out["power_kw"] = _parse_power_kw(value)
    return out


def _listing_to_stub(item: dict) -> ListingStub | None:
    vehicle = item.get("vehicle") or {}
    make = vehicle.get("make")
    model = vehicle.get("model")
    if not item.get("id"):
        return None

    url = item.get("url") or ""
    url = url if url.startswith("http") else f"{BASE_URL}{url}"
    price_fmt = (item.get("price") or {}).get("priceFormatted")
    images = item.get("images") or []
    loc = item.get("location") or {}
    details = _details_map(item.get("vehicleDetails") or [])

    title = " ".join(p for p in (make, model, vehicle.get("modelVersionInput")) if p)
    tags = [
        t for t in (
            f"{details.get('mileage_km')} km" if details.get("mileage_km") else None,
            f"EZ {details.get('year')}" if details.get("year") else None,
            vehicle.get("fuel"),
        ) if t
    ]
    stub = ListingStub(
        source=SOURCE,
        source_id=str(item["id"]),
        url=url,
        title=title,
        price_hint=price_fmt,
        location_hint=" ".join(p for p in (loc.get("zip"), loc.get("city")) if p) or None,
        image_hint=images[0] if images else None,
        tags=tags,
        description_hint=vehicle.get("subtitle") or vehicle.get("modelVersionInput"),
    )
    # Stash the structured fields for basic_specs (avoids re-parsing).
    stub._as24 = {  # type: ignore[attr-defined]
        "price": _to_int(price_fmt),
        "price_negotiable": False,
        "make": make,
        "model": model,
        "variant": vehicle.get("modelVersionInput"),
        "fuel": _map_fuel(vehicle.get("fuel")),
        "transmission": _map_transmission(vehicle.get("transmission")),
        "seller_type": (item.get("seller") or {}).get("type", "").lower() or None,
        "location_city": loc.get("city"),
        "location_plz": loc.get("zip"),
        **details,
    }
    return stub


def parse_search_html(html: str) -> list[ListingStub]:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.find("script", id="__NEXT_DATA__")
    if node is None or not node.string:
        return []
    try:
        data = json.loads(node.string)
    except json.JSONDecodeError:
        return []
    listings = (
        data.get("props", {}).get("pageProps", {}).get("listings", []) or []
    )
    stubs = [_listing_to_stub(item) for item in listings]
    return [s for s in stubs if s is not None]


def build_search_url(filters: StructuredFilters, page: int = 1) -> str:
    path = "/lst"
    if filters.make:
        path += f"/{_slug(filters.make)}"
        if filters.model:
            path += f"/{_slug(filters.model)}"
    params = [("atype", "C"), ("cy", "D"), ("sort", "standard"), ("desc", "0"),
              ("page", str(page)), ("size", "20")]
    if filters.price_min is not None:
        params.append(("pricefrom", str(filters.price_min)))
    if filters.price_max is not None:
        params.append(("priceto", str(filters.price_max)))
    if filters.mileage_max is not None:
        params.append(("kmto", str(filters.mileage_max)))
    if filters.year_min is not None:
        params.append(("fregfrom", str(filters.year_min)))
    if filters.year_max is not None:
        params.append(("fregto", str(filters.year_max)))
    query = "&".join(f"{k}={v}" for k, v in params)
    return f"{BASE_URL}{path}?{query}"


class AutoScout24Scraper(Scraper):
    name = SOURCE
    base_url = BASE_URL
    # The __NEXT_DATA__ fields are still used as a seed via basic_specs, but the agent
    # (P2) decides make/model/variant from the announcement text so the dashboard model
    # facet is agent-categorized consistently across all sources.
    provides_structured_data = False

    def __init__(self, firecrawl: FirecrawlClient) -> None:
        self._fc = firecrawl

    async def search(
        self, filters: StructuredFilters, *, max_pages: int
    ) -> AsyncIterator[ListingStub]:
        for page in range(1, max_pages + 1):
            url = build_search_url(filters, page)
            try:
                # rawHtml preserves the __NEXT_DATA__ script (cleaned `html` strips it).
                data = await self._fc.scrape(
                    url, formats=["rawHtml"], only_main_content=False
                )
            except Exception as exc:  # noqa: BLE001 — transient page error shouldn't fail the run
                logger.warning("autoscout24 page %s failed, stopping paging: %s", page, exc)
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
        m = _UUID_RE.search(url)
        return m.group(1) if m else url.rstrip("/").rsplit("/", 1)[-1]

    def basic_specs(self, stub: ListingStub) -> dict:
        specs = getattr(stub, "_as24", {})
        return {k: v for k, v in specs.items() if v is not None}
