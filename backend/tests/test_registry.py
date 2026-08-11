"""Registry wiring: both v1 sources are registered under their source name."""

from __future__ import annotations

from carcatcher.scraping.autoscout24 import AutoScout24Parser
from carcatcher.scraping.registry import build_registry
from carcatcher.scraping.vwde import VwDeParser


def test_registry_has_both_v1_sources():
    registry = build_registry()
    assert set(registry.keys()) == {"autoscout24", "vw"}
    assert isinstance(registry["autoscout24"], AutoScout24Parser)
    assert isinstance(registry["vw"], VwDeParser)
