"""Process-wide singleton: the parser registry. Built in the FastAPI lifespan;
overridable in tests via `set_state`."""

from __future__ import annotations

from dataclasses import dataclass

from carcatcher.scraping.base import Parser
from carcatcher.scraping.registry import build_registry


@dataclass
class AppState:
    parsers: dict[str, Parser]


_state: AppState | None = None


def build_state() -> AppState:
    return AppState(parsers=build_registry())


def set_state(state: AppState | None) -> None:
    global _state
    _state = state


def get_state() -> AppState:
    if _state is None:
        raise RuntimeError("AppState not initialized")
    return _state
