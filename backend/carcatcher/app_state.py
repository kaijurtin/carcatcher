"""Process-wide singletons: Firecrawl client, scrapers, AI extractor, scheduler,
and the in-process crawl lock. Built in the FastAPI lifespan; overridable in tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from carcatcher.ai.client import AIClient
from carcatcher.ai.evaluate import Evaluator
from carcatcher.ai.nl_search import Translator
from carcatcher.ai.ollama_client import OllamaClient
from carcatcher.ai.recommend import Recommender
from carcatcher.config import Settings, get_settings
from carcatcher.normalization.extractor import Extractor
from carcatcher.scraping.base import Scraper
from carcatcher.scraping.firecrawl_client import FirecrawlClient
from carcatcher.scraping.registry import build_registry

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler


@dataclass
class AppState:
    firecrawl: FirecrawlClient
    scrapers: dict[str, Scraper]
    ai: AIClient
    extractor: Extractor
    evaluator: Evaluator
    translator: Translator
    recommender: Recommender
    scheduler: "AsyncIOScheduler | None" = None
    crawl_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_state: AppState | None = None


def build_state(settings: Settings | None = None) -> AppState:
    settings = settings or get_settings()
    firecrawl = FirecrawlClient(settings)
    scrapers = build_registry(firecrawl)
    ai = AIClient(settings)
    # AI provider is pluggable across ALL roles. ai_provider=ollama routes
    # normalize/evaluate/translate/recommend to a local OpenAI-compatible model
    # (fully offline, $0); anthropic keeps the hosted client. `ai` is always built
    # so `state.ai` and a flip back to anthropic keep working.
    provider = OllamaClient(settings) if settings.ai_provider == "ollama" else ai
    return AppState(
        firecrawl=firecrawl,
        scrapers=scrapers,
        ai=ai,
        extractor=Extractor(provider),
        evaluator=Evaluator(provider),
        translator=Translator(provider),
        recommender=Recommender(provider),
    )


def set_state(state: AppState | None) -> None:
    global _state
    _state = state


def get_state() -> AppState:
    if _state is None:
        raise RuntimeError("AppState not initialized")
    return _state
