"""Scraper registry. Adding a site = build its Scraper here + register it."""

from __future__ import annotations

from carcatcher.scraping.base import Scraper
from carcatcher.scraping.firecrawl_client import FirecrawlClient
from carcatcher.scraping.kleinanzeigen import KleinanzeigenScraper


def build_registry(firecrawl: FirecrawlClient) -> dict[str, Scraper]:
    scrapers: list[Scraper] = [
        KleinanzeigenScraper(firecrawl),
        # AutoScout24Scraper(firecrawl),  # P9
        # MobileDeScraper(firecrawl),     # P9
    ]
    return {s.name: s for s in scrapers}
