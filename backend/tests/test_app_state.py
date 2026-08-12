"""Tests for process-wide AppState construction."""

from __future__ import annotations

from carcatcher.app_state import build_state
from carcatcher.geocoding import NominatimGeocoder


def test_build_state_wires_a_real_geocoder():
    state = build_state()
    assert isinstance(state.geocoder, NominatimGeocoder)
