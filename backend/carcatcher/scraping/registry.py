"""Parser registry: source name -> Parser instance."""

from __future__ import annotations

from carcatcher.scraping.autoscout24 import AutoScout24Parser
from carcatcher.scraping.base import Parser
from carcatcher.scraping.vwde import VwDeParser


def build_registry() -> dict[str, Parser]:
    parsers: list[Parser] = [AutoScout24Parser(), VwDeParser()]
    return {p.name: p for p in parsers}
