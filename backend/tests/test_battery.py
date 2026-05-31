"""Tests for EV battery capacity + State of Health feature."""

from __future__ import annotations

from carcatcher.normalization.schema import NormalizedListing


def test_battery_kwh_accepts_valid_capacity():
    norm = NormalizedListing(battery_kwh=77.0)
    assert norm.battery_kwh == 77.0


def test_battery_kwh_rejects_out_of_range():
    # 5 kWh is implausibly small, 500 kWh implausibly large -> coerced to None
    assert NormalizedListing(battery_kwh=5).battery_kwh is None
    assert NormalizedListing(battery_kwh=500).battery_kwh is None


def test_soh_pct_clamps_out_of_range_to_none():
    assert NormalizedListing(battery_soh_pct=92).battery_soh_pct == 92
    assert NormalizedListing(battery_soh_pct=150).battery_soh_pct is None
    assert NormalizedListing(battery_soh_pct=-3).battery_soh_pct is None


def test_battery_fields_default_none():
    norm = NormalizedListing()
    assert norm.battery_kwh is None
    assert norm.battery_soh_pct is None


def test_battery_bounds_are_inclusive():
    # Confirms the validators use inclusive (<=) bounds at the edges.
    assert NormalizedListing(battery_kwh=10.0).battery_kwh == 10.0
    assert NormalizedListing(battery_kwh=250.0).battery_kwh == 250.0
    assert NormalizedListing(battery_kwh=9.9).battery_kwh is None
    assert NormalizedListing(battery_soh_pct=0).battery_soh_pct == 0
    assert NormalizedListing(battery_soh_pct=100).battery_soh_pct == 100


from carcatcher.normalization.prompts import NORMALIZATION_SYSTEM
from carcatcher.normalization.schema import NORMALIZED_TOOL_SCHEMA


def test_tool_schema_exposes_battery_fields():
    props = NORMALIZED_TOOL_SCHEMA["properties"]
    assert "battery_kwh" in props
    assert "battery_soh_pct" in props


def test_prompt_mentions_battery_and_reichweite_guard():
    # Must instruct extraction and must warn that Reichweite (range) != capacity.
    assert "battery_kwh" in NORMALIZATION_SYSTEM
    assert "battery_soh_pct" in NORMALIZATION_SYSTEM
    assert "Reichweite" in NORMALIZATION_SYSTEM
