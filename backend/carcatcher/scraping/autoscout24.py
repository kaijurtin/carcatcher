"""AutoScout24.de parser (source: "autoscout24").

Plain HTTP GET — no rendering needed. AS24 is a Next.js app that embeds its search
results as a `<script id="__NEXT_DATA__">` JSON blob in the initial server-rendered
HTML (verified live 2026-08-11: a plain `curl` with a browser-like User-Agent
returns it directly, no headless browser required).
"""

from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from carcatcher.scraping.base import Model, Parser, RawListing

SOURCE = "autoscout24"
BASE_URL = "https://www.autoscout24.de"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_MODEL_SLUGS: dict[Model, str] = {"id3": "id-3", "id4": "id-4"}
_DIGITS_RE = re.compile(r"\d[\d.]*")
_UUID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
_POWER_RE = re.compile(r"(\d+)\s*kW")
_YEAR_RE = re.compile(r"(\d{4})")


def _to_int(text: str | None) -> int | None:
    if not text:
        return None
    m = _DIGITS_RE.search(text)
    if not m:
        return None
    digits = m.group(0).replace(".", "")
    return int(digits) if digits.isdigit() else None


def _details(vehicle_details: list) -> dict:
    out: dict = {}
    for d in vehicle_details or []:
        icon, value = d.get("iconName"), d.get("data")
        if icon == "mileage_odometer":
            out["mileage_km"] = _to_int(value)
        elif icon == "calendar":
            m = _YEAR_RE.search(value or "")
            out["year"] = int(m.group(1)) if m else None
        elif icon == "speedometer":
            m = _POWER_RE.search(value or "")
            out["power_kw"] = int(m.group(1)) if m else None
    return out


def _source_id(url: str) -> str:
    m = _UUID_RE.search(url)
    return m.group(1) if m else url.rstrip("/").rsplit("/", 1)[-1]


def _condition(vehicle: dict) -> str:
    return "new" if (vehicle.get("offerType") or "").strip().upper() == "N" else "used"


def _item_to_listing(item: dict, model: Model) -> RawListing | None:
    if not item.get("id"):
        return None
    vehicle = item.get("vehicle") or {}
    url = item.get("url") or ""
    url = url if url.startswith("http") else f"{BASE_URL}{url}"
    details = _details(item.get("vehicleDetails") or [])
    loc = item.get("location") or {}
    return RawListing(
        source=SOURCE,
        source_id=_source_id(url),
        url=url,
        model=model,
        trim=vehicle.get("modelVersionInput") or vehicle.get("subtitle") or "",
        price_eur=_to_int((item.get("price") or {}).get("priceFormatted")),
        mileage_km=details.get("mileage_km"),
        year=details.get("year"),
        power_kw=details.get("power_kw"),
        condition=_condition(vehicle),
        location=" ".join(p for p in (loc.get("zip"), loc.get("city")) if p) or None,
        title=" ".join(
            p for p in (vehicle.get("make"), vehicle.get("model"), vehicle.get("modelVersionInput"))
            if p
        ),
    )


def parse_search_html(html: str, model: Model) -> list[RawListing]:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.find("script", id="__NEXT_DATA__")
    if node is None or not node.string:
        return []
    try:
        import json

        data = json.loads(node.string)
    except ValueError:
        return []
    items = data.get("props", {}).get("pageProps", {}).get("listings", []) or []
    out = [_item_to_listing(item, model) for item in items]
    return [l for l in out if l is not None]


def build_search_url(model: Model, page: int) -> str:
    slug = _MODEL_SLUGS[model]
    params = "&".join(["atype=C", "cy=D", "sort=standard", "desc=0", f"page={page}", "size=20"])
    return f"{BASE_URL}/lst/volkswagen/{slug}?{params}"


class AutoScout24Parser(Parser):
    name = SOURCE

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=20.0, headers={"User-Agent": USER_AGENT})

    def fetch_listings(self, model: Model) -> list[RawListing]:
        results: list[RawListing] = []
        for page in range(1, 6):  # AS24 pages ~20/each; 5 pages covers this source's v1 volume
            resp = self._client.get(build_search_url(model, page))
            resp.raise_for_status()
            page_listings = parse_search_html(resp.text, model)
            if not page_listings:
                break
            results.extend(page_listings)
        return results
