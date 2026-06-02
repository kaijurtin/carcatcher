"""Async client over the self-hosted Firecrawl API.

Centralizes politeness: a global concurrency semaphore + a jittered minimum
interval between requests, so every site fetch (search and detail) is throttled
regardless of caller. This is the single choke point the risk model relies on.
"""

from __future__ import annotations

import asyncio
import random

import httpx

from carcatcher.config import Settings, get_settings


class FirecrawlError(RuntimeError):
    pass


class FirecrawlClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._s = settings or get_settings()
        self._client = client or httpx.AsyncClient(timeout=60.0)
        self._owns_client = client is None
        self._sem = asyncio.Semaphore(max(1, self._s.firecrawl_concurrency))
        self._lock = asyncio.Lock()
        self._last_ts: float = 0.0

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _throttle(self) -> None:
        """Enforce a jittered minimum gap between consecutive requests."""
        min_interval = self._s.scrape_min_interval_ms / 1000.0
        async with self._lock:
            now = asyncio.get_event_loop().time()
            wait = self._last_ts + min_interval - now
            if wait > 0:
                await asyncio.sleep(wait + random.uniform(0, min_interval * 0.3))
            self._last_ts = asyncio.get_event_loop().time()

    async def scrape(
        self,
        url: str,
        *,
        formats: list[str] | None = None,
        only_main_content: bool = True,
    ) -> dict:
        """Scrape a single URL, returning Firecrawl's `data` object
        (keys: markdown / html / rawHtml / metadata, depending on `formats`)."""
        payload: dict = {
            "url": url,
            "formats": formats or ["markdown"],
            "onlyMainContent": only_main_content,
        }
        headers = {}
        if self._s.firecrawl_api_key:
            headers["Authorization"] = f"Bearer {self._s.firecrawl_api_key}"

        async with self._sem:
            await self._throttle()
            try:
                resp = await self._client.post(
                    f"{self._s.firecrawl_base_url}/v1/scrape",
                    json=payload,
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                raise FirecrawlError(f"request to Firecrawl failed: {exc}") from exc

        if resp.status_code != 200:
            raise FirecrawlError(
                f"Firecrawl returned {resp.status_code} for {url}: {resp.text[:200]}"
            )
        body = resp.json()
        if not body.get("success", False):
            raise FirecrawlError(f"Firecrawl unsuccessful for {url}: {body!r}")
        return body.get("data", {})

    async def search(self, query: str, *, limit: int = 6) -> list[dict]:
        """Web search via Firecrawl, returning the `data` list of
        `{url, title, description}` results (empty list on no hits)."""
        payload: dict = {"query": query, "limit": limit}
        headers = {}
        if self._s.firecrawl_api_key:
            headers["Authorization"] = f"Bearer {self._s.firecrawl_api_key}"

        async with self._sem:
            await self._throttle()
            try:
                resp = await self._client.post(
                    f"{self._s.firecrawl_base_url}/v1/search",
                    json=payload,
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                raise FirecrawlError(f"request to Firecrawl failed: {exc}") from exc

        if resp.status_code != 200:
            raise FirecrawlError(
                f"Firecrawl search returned {resp.status_code} for "
                f"{query!r}: {resp.text[:200]}"
            )
        body = resp.json()
        if not body.get("success", False):
            raise FirecrawlError(f"Firecrawl search unsuccessful for {query!r}: {body!r}")
        return body.get("data", [])
