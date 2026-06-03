"""mobile.de scraper (source: "mobilede").

mobile.de is a React/loadable SSR app behind DataDome; in production Firecrawl
renders it. The search results live in **window.__INITIAL_STATE__** at
`search.srp.data.searchResults.items` — there is NO vehicle JSON-LD (only org/
breadcrumb), which is why an earlier JSON-LD parser found nothing.

We extract the cheap card fields (price/year/mileage/power/fuel/transmission/location/
seller) deterministically from each item's `attr`, and provide `make`/`model` as a
seed. `provides_structured_data = False`, so the agent (P2 normalization) reads the
announcement text and decides make/model/variant — that agent-decided model is what
drives the dashboard model facet. Make targeting uses `ms=<makeId>`.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator

from carcatcher.normalization.makes import canonical_make
from carcatcher.scraping.base import ListingStub, RawPage, Scraper
from carcatcher.scraping.firecrawl_client import FirecrawlClient
from carcatcher.schemas import StructuredFilters

logger = logging.getLogger(__name__)

SOURCE = "mobilede"
BASE_URL = "https://suchen.mobile.de"

_ID_RE = re.compile(r"[?&]id=(\d+)")

# Verified mobile.de make IDs (URL param `ms=<makeId>`). German-market makes.
_MAKE_IDS = {
    "volkswagen": 25200, "audi": 1900, "bmw": 3500, "mercedes-benz": 17200,
    "opel": 19000, "ford": 9000, "skoda": 22900, "seat": 22500, "cupra": 3,
    "renault": 20700, "peugeot": 19300, "fiat": 8800, "dacia": 6600,
    "hyundai": 11600, "kia": 13200, "tesla": 135, "toyota": 24100,
    "nissan": 18700, "volvo": 25100, "mazda": 16800, "mini": 17500,
}

_FUEL_MAP = {
    "benzin": "petrol", "diesel": "diesel", "elektro": "electric",
    "hybrid": "hybrid", "autogas": "lpg", "lpg": "lpg", "erdgas": "cng", "cng": "cng",
}
_TRANSMISSION_MAP = {
    "manuell": "manual", "schaltgetriebe": "manual",
    "automatik": "automatic", "halbautomatik": "automatic",
}


def _to_int(value) -> int | None:
    if value is None:
        return None
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def _map(table: dict, value) -> str | None:
    return table.get(str(value).strip().lower()) if value else None


def _year(fr: str | None) -> int | None:
    # "05/2018" -> 2018
    if not fr:
        return None
    m = re.search(r"(\d{4})", str(fr))
    return int(m.group(1)) if m else None


def _power_kw(pw: str | None) -> int | None:
    # "85 kW (116 PS)" -> 85
    if not pw:
        return None
    m = re.search(r"(\d+)\s*kW", str(pw))
    return int(m.group(1)) if m else None


def _seller(type_localized: str | None) -> str | None:
    t = (type_localized or "").strip().lower()
    if t.startswith("händler") or t.startswith("haendler"):
        return "dealer"
    if t.startswith("privat"):
        return "private"
    return None


def extract_initial_state(html: str) -> str | None:
    """Return the JSON text of `window.__INITIAL_STATE__ = {...}` (brace-matched)."""
    i = html.find("__INITIAL_STATE__")
    if i < 0:
        return None
    j = html.find("=", i) + 1
    while j < len(html) and html[j] in " \n\t\r":
        j += 1
    if j >= len(html) or html[j] != "{":
        return None
    depth = 0
    in_str = False
    esc = False
    for k in range(j, len(html)):
        c = html[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return html[j:k + 1]
    return None


def _item_to_stub(item: dict) -> ListingStub | None:
    if not isinstance(item, dict) or item.get("isEyeCatcher") or not item.get("id"):
        return None
    rel = item.get("relativeUrl") or ""
    url = rel if rel.startswith("http") else f"{BASE_URL}{rel}"
    attr = item.get("attr") or {}
    price = item.get("price") or {}
    price_amount = price.get("grossAmount")
    image = (item.get("previewImage") or {}).get("src")
    contact = item.get("contactInfo") or {}
    make = item.get("make")
    model = item.get("model")
    title = item.get("title") or " ".join(p for p in (make, model) if p)
    sub = item.get("subTitle")

    stub = ListingStub(
        source=SOURCE,
        source_id=str(item["id"]),
        url=url,
        title=title,
        price_hint=price.get("gross") or (f"{price_amount} €" if price_amount else None),
        location_hint=" ".join(p for p in (attr.get("z"), attr.get("loc")) if p) or None,
        image_hint=image,
        tags=[t for t in (
            attr.get("ml"),
            f"EZ {attr['fr']}" if attr.get("fr") else None,
            attr.get("ft"),
        ) if t],
        description_hint=" · ".join(p for p in (title, sub) if p) or title,
    )
    stub._mde = {  # type: ignore[attr-defined]
        "price": _to_int(price_amount),
        "make": canonical_make(make),
        "model": model,
        "year": _year(attr.get("fr")),
        "mileage_km": _to_int(attr.get("ml")),
        "power_kw": _power_kw(attr.get("pw")),
        "fuel": _map(_FUEL_MAP, attr.get("ft")),
        "transmission": _map(_TRANSMISSION_MAP, attr.get("tr")),
        "seller_type": _seller(contact.get("typeLocalized")),
        "location_city": attr.get("loc"),
        "location_plz": attr.get("z"),
    }
    return stub


def parse_search_html(html: str) -> list[ListingStub]:
    state = extract_initial_state(html)
    if not state:
        return []
    try:
        data = json.loads(state)
    except json.JSONDecodeError:
        return []
    try:
        items = data["search"]["srp"]["data"]["searchResults"]["items"]
    except (KeyError, TypeError):
        return []
    stubs: list[ListingStub] = []
    seen: set[str] = set()
    for item in items or []:
        stub = _item_to_stub(item)
        if stub and stub.source_id not in seen:
            seen.add(stub.source_id)
            stubs.append(stub)
    return stubs


def _make_id(make: str | None) -> int | None:
    if not make:
        return None
    mid = _MAKE_IDS.get(make.strip().lower())
    if mid is None:
        cm = canonical_make(make)  # VW -> Volkswagen, etc.
        mid = _MAKE_IDS.get((cm or "").strip().lower())
    return mid


# mobile.de fuel-type URL param (`ft`). Verified live: `ft=ELECTRICITY` narrows the
# result set to EVs. Without it the `ms` make filter returns the whole catalogue
# (petrol Golfs etc.), so electric searches surfaced nothing. mobile.de does NOT
# honour a free-text model in `ms` (`ms=<makeId>;;<model>` was verified to be
# ignored), so fuel is the only reliable URL-level narrowing we have.
_FT_PARAM = {
    "electric": "ELECTRICITY",
    "petrol": "PETROL",
    "diesel": "DIESEL",
    "hybrid": "HYBRID",
    "lpg": "LPG",
    "cng": "CNG",
}


def build_search_url(filters: StructuredFilters, page: int = 1) -> str:
    params = [("isSearchRequest", "true"), ("s", "Car"), ("vc", "Car"), ("pageNumber", str(page))]
    mid = _make_id(filters.make)
    if mid is not None:
        params.append(("ms", str(mid)))  # make targeting (mobile.de ignores free-text model)
    ft = _FT_PARAM.get((filters.fuel or "").strip().lower())
    if ft is not None:
        params.append(("ft", ft))
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
    provides_structured_data = False  # agent decides make/model/variant from the text

    def __init__(self, firecrawl: FirecrawlClient) -> None:
        self._fc = firecrawl

    async def search(
        self, filters: StructuredFilters, *, max_pages: int
    ) -> AsyncIterator[ListingStub]:
        for page in range(1, max_pages + 1):
            url = build_search_url(filters, page)
            try:
                # rawHtml preserves the inline __INITIAL_STATE__ script.
                data = await self._fc.scrape(url, formats=["rawHtml"], only_main_content=False)
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
