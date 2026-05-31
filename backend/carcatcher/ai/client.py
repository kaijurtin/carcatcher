"""Anthropic SDK wrapper.

Centralizes: model tiering, prompt caching (system prompts are cached so only the
per-listing content varies), tool-forced structured output, retry/backoff, usage +
cost accounting, and the global AI_DISABLED kill switch.
"""

from __future__ import annotations

import asyncio
import logging

from carcatcher.ai.models import SPECS, Usage, estimate_cost
from carcatcher.config import Settings, get_settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 1.5


class AIDisabledError(RuntimeError):
    """Raised when an AI call is attempted while AI is disabled / unconfigured."""


class StructuredResult:
    def __init__(self, data: dict, usage: Usage, model: str) -> None:
        self.data = data
        self.usage = usage
        self.model = model
        self.cost_usd = estimate_cost(model, usage)


class AIClient:
    def __init__(self, settings: Settings | None = None, *, client=None) -> None:
        self._s = settings or get_settings()
        self._client = client  # injectable AsyncAnthropic (or test double)

    @property
    def enabled(self) -> bool:
        if self._s.ai_disabled:
            return False
        return self._client is not None or bool(self._s.anthropic_api_key)

    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self._s.anthropic_api_key)
        return self._client

    async def extract_structured(
        self,
        *,
        model: str,
        cached_system: str,
        user_text: str,
        tool_name: str,
        tool_schema: dict,
        tool_description: str = "",
        max_tokens: int | None = None,
    ) -> StructuredResult:
        """Force a single tool call and return its validated input as a dict."""
        if not self.enabled:
            raise AIDisabledError("AI is disabled or ANTHROPIC_API_KEY is missing")

        spec = SPECS.get(model)
        max_toks = max_tokens or (spec.max_tokens if spec else 1024)
        client = self._get_client()

        kwargs = dict(
            model=model,
            max_tokens=max_toks,
            system=[
                {
                    "type": "text",
                    "text": cached_system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[
                {
                    "name": tool_name,
                    "description": tool_description,
                    "input_schema": tool_schema,
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": user_text}],
        )

        resp = await self._call_with_retry(client, kwargs)
        data = _extract_tool_input(resp, tool_name)
        usage = Usage(
            input_tokens=getattr(resp.usage, "input_tokens", 0),
            output_tokens=getattr(resp.usage, "output_tokens", 0),
        )
        return StructuredResult(data=data, usage=usage, model=model)

    async def _call_with_retry(self, client, kwargs: dict):
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return await client.messages.create(**kwargs)
            except Exception as exc:  # noqa: BLE001 — narrowed below
                if not _is_retryable(exc) or attempt == _MAX_RETRIES - 1:
                    raise
                last_exc = exc
                delay = _BACKOFF_BASE**attempt
                logger.warning("Anthropic call failed (attempt %s), retrying in %.1fs: %s",
                               attempt + 1, delay, exc)
                await asyncio.sleep(delay)
        raise last_exc  # pragma: no cover


def _extract_tool_input(resp, tool_name: str) -> dict:
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            return dict(getattr(block, "input", {}) or {})
    raise ValueError(f"no tool_use block named {tool_name!r} in response")


def _is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status in (408, 409, 429, 500, 502, 503, 504):
        return True
    # Connection-level errors expose no status code.
    return status is None and "connection" in type(exc).__name__.lower()
