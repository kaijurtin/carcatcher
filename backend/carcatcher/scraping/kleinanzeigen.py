"""Kleinanzeigen.de scraper (source: "kleinanzeigen").

The parsing + URL building are pure functions so they can be unit-tested against
committed HTML fixtures with no network. Firecrawl is only the fetch/render
backend. Anti-bot posture: low volume, throttled in FirecrawlClient, "Gesuch"
(wanted-to-buy) ads are skipped.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator

from bs4 import BeautifulSoup

from carcatcher.scraping.base import ListingStub, RawPage, Scraper
from carcatcher.scraping.firecrawl_client import FirecrawlClient
from carcatcher.schemas import StructuredFilters

logger = logging.getLogger(__name__)

SOURCE = "kleinanzeigen"
BASE_URL = "https://www.kleinanzeigen.de"
AUTOS_CATEGORY = "c216"

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_ID_RE = re.compile(r"/(\d+)-\d+-\d+/?$")
_KM_RE = re.compile(r"([\d.]+)\s*km", re.IGNORECASE)
_EZ_RE = re.compile(r"EZ\s*(?:\d{1,2}/)?(\d{4})", re.IGNORECASE)
_PRICE_RE = re.compile(r"([\d.]+)\s*€")


def _to_int(num: str) -> int | None:
    digits = num.replace(".", "").replace(" ", "").strip()
    return int(digits) if digits.isdigit() else None


def parse_card_specs(price_hint: str | None, tags: list[str]) -> dict:
    """Extract the deterministic card facts: price, negotiable, mileage, year."""
    specs: dict = {}
    if price_hint:
        m = _PRICE_RE.search(price_hint)
        if m:
            specs["price"] = _to_int(m.group(1))
        specs["price_negotiable"] = "VB" in price_hint or "Verhandlung" in price_hint
    for tag in tags:
        km = _KM_RE.search(tag)
        if km:
            val = _to_int(km.group(1))
            if val is not None:
                specs["mileage_km"] = val
        ez = _EZ_RE.search(tag)
        if ez:
            specs["year"] = int(ez.group(1))
    return specs


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower().strip()).strip("-")


def build_search_url(filters: StructuredFilters, page: int = 1) -> str:
    """Build a Kleinanzeigen autos search URL (path-based).

    Approximate — make/model are passed as a keyword slug rather than category
    slugs. Validated against the live site on deploy; the parser is what's
    fixture-tested.
    """
    segments = ["s-autos"]
    if page > 1:
        segments.append(f"seite:{page}")

    keyword = filters.keywords or " ".join(
        p for p in (filters.make, filters.model) if p
    )
    if keyword.strip():
        segments.append(_slugify(keyword))

    if filters.price_min is not None or filters.price_max is not None:
        lo = filters.price_min if filters.price_min is not None else ""
        hi = filters.price_max if filters.price_max is not None else ""
        segments.append(f"preis:{lo}:{hi}")

    segments.append(AUTOS_CATEGORY)
    return f"{BASE_URL}/" + "/".join(segments)


def _card_to_stub(article) -> ListingStub | None:
    """Parse one `article.aditem` element into a ListingStub. Returns None for
    wanted-to-buy ("Gesuch") ads, which are not purchasable listings."""
    tags = [t.get_text(strip=True) for t in article.select(".simpletag")]
    if any("Gesuch" in t for t in tags):
        return None

    adid = article.get("data-adid")
    href = article.get("data-href")
    title_el = article.select_one("h2 a, .text-module-begin a, a.ellipsis")
    if href is None and title_el is not None:
        href = title_el.get("href")
    if not href:
        return None
    if not adid:
        m = _ID_RE.search(href)
        adid = m.group(1) if m else href.rstrip("/").rsplit("/", 1)[-1].split("-")[0]

    url = href if href.startswith("http") else f"{BASE_URL}{href}"
    title = title_el.get_text(strip=True) if title_el else ""

    price_el = article.select_one(".aditem-main--middle--price-shipping--price")
    loc_el = article.select_one(".aditem-main--top--left")
    desc_el = article.select_one(".aditem-main--middle--description")
    img_el = article.select_one("img")
    image = None
    if img_el is not None:
        image = img_el.get("src") or img_el.get("data-imgsrc") or img_el.get("srcset")

    return ListingStub(
        source=SOURCE,
        source_id=str(adid),
        url=url,
        title=title,
        price_hint=price_el.get_text(strip=True) if price_el else None,
        location_hint=" ".join(loc_el.get_text(strip=True).split()) if loc_el else None,
        image_hint=image,
        tags=[t for t in tags if t != "Gesuch"],
        description_hint=desc_el.get_text(strip=True) if desc_el else None,
    )


def parse_search_html(html: str) -> list[ListingStub]:
    """Parse a Kleinanzeigen results page into stubs (Gesuch ads excluded)."""
    soup = BeautifulSoup(html, "html.parser")
    stubs: list[ListingStub] = []
    for article in soup.select("article.aditem"):
        stub = _card_to_stub(article)
        if stub is not None:
            stubs.append(stub)
    return stubs


class KleinanzeigenScraper(Scraper):
    name = SOURCE
    base_url = BASE_URL

    def __init__(self, firecrawl: FirecrawlClient) -> None:
        self._fc = firecrawl

    async def search(
        self, filters: StructuredFilters, *, max_pages: int
    ) -> AsyncIterator[ListingStub]:
        for page in range(1, max_pages + 1):
            url = build_search_url(filters, page)
            try:
                data = await self._fc.scrape(
                    url, formats=["html"], only_main_content=False
                )
            except Exception as exc:  # noqa: BLE001 — transient page error shouldn't fail the run
                logger.warning("kleinanzeigen page %s failed, stopping paging: %s", page, exc)
                break
            html = data.get("html") or data.get("rawHtml") or ""
            stubs = parse_search_html(html)
            if not stubs:
                break  # no more results
            for stub in stubs:
                yield stub

    async def fetch_detail(self, url: str) -> RawPage:
        data = await self._fc.scrape(url, formats=["markdown", "html"])
        return RawPage(
            url=url,
            markdown=data.get("markdown", ""),
            html=data.get("html"),
            images=(data.get("metadata", {}) or {}).get("images", []) or [],
        )

    def parse_source_id(self, url: str) -> str:
        m = _ID_RE.search(url)
        if m:
            return m.group(1)
        return url.rstrip("/").rsplit("/", 1)[-1].split("-")[0]

    def basic_specs(self, stub: ListingStub) -> dict:
        return parse_card_specs(stub.price_hint, stub.tags)
