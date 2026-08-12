"""Tests for battery-capacity extraction from free-text trim/title strings."""

from __future__ import annotations

from carcatcher.scraping.battery import parse_battery_kwh


def test_parses_whole_number_kwh():
    assert parse_battery_kwh("Pro 82 kWh") == 82.0


def test_parses_comma_decimal_kwh():
    assert parse_battery_kwh("Pure 58,0 kWh Performance") == 58.0


def test_parses_dot_decimal_kwh():
    assert parse_battery_kwh("Pure 58.5 kWh") == 58.5


def test_is_case_insensitive():
    assert parse_battery_kwh("Pro 82 KWH") == 82.0


def test_returns_none_when_no_match_in_any_text():
    assert parse_battery_kwh("Pro Performance", "VW ID.4 Pro Performance") is None


def test_returns_none_for_none_and_empty_strings():
    assert parse_battery_kwh(None, "", None) is None


def test_uses_first_matching_text_in_order():
    assert parse_battery_kwh("Pure", "Pro 82 kWh") == 82.0


def test_prefers_first_text_over_second_when_both_match():
    assert parse_battery_kwh("Pro 58 kWh", "Pro 82 kWh") == 58.0
