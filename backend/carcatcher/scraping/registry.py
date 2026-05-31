"""Scraper registry. Adding a site = build its Scraper here + register it."""

from __future__ import annotations

from carcatcher.scraping.autoscout24 import AutoScout24Scraper
from carcatcher.scraping.base import Scraper
from carcatcher.scraping.firecrawl_client import FirecrawlClient
from carcatcher.scraping.kleinanzeigen import KleinanzeigenScraper
from carcatcher.scraping.mobilede import MobileDeScraper


def build_registry(firecrawl: FirecrawlClient) -> dict[str, Scraper]:
    scrapers: list[Scraper] = [
        KleinanzeigenScraper(firecrawl),
        AutoScout24Scraper(firecrawl),
        MobileDeScraper(firecrawl),
    ]
    return {s.name: s for s in scrapers}
