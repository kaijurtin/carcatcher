"""FirecrawlClient HTTP contract tests (mocked transport via respx)."""

from __future__ import annotations

import httpx
import pytest
import respx

from carcatcher.config import Settings
from carcatcher.scraping.firecrawl_client import FirecrawlClient, FirecrawlError
from carcatcher.scraping.registry import build_registry

BASE = "http://firecrawl-test:3002"


def _settings() -> Settings:
    return Settings(
        firecrawl_base_url=BASE,
        scrape_min_interval_ms=0,  # no throttle delay in tests
        firecrawl_concurrency=2,
    )


@respx.mock
async def test_scrape_returns_data():
    route = respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(
            200, json={"success": True, "data": {"html": "<html>ok</html>"}}
        )
    )
    client = FirecrawlClient(_settings())
    try:
        data = await client.scrape("https://example.com", formats=["html"])
    finally:
        await client.aclose()
    assert data["html"] == "<html>ok</html>"
    assert route.called


@respx.mock
async def test_scrape_raises_on_http_error():
    respx.post(f"{BASE}/v1/scrape").mock(return_value=httpx.Response(503, text="down"))
    client = FirecrawlClient(_settings())
    with pytest.raises(FirecrawlError):
        await client.scrape("https://example.com")
    await client.aclose()


@respx.mock
async def test_scrape_raises_on_unsuccessful_body():
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(200, json={"success": False, "error": "blocked"})
    )
    client = FirecrawlClient(_settings())
    with pytest.raises(FirecrawlError):
        await client.scrape("https://example.com")
    await client.aclose()


def test_registry_contains_kleinanzeigen():
    reg = build_registry(firecrawl=None)  # type: ignore[arg-type]
    assert "kleinanzeigen" in reg
    assert reg["kleinanzeigen"].name == "kleinanzeigen"
