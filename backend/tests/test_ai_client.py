"""AIClient tests: tool extraction, caching headers, retry, kill switch, cost."""

from __future__ import annotations

import pytest

from carcatcher.ai.client import AIClient, AIDisabledError
from carcatcher.ai.models import HAIKU
from carcatcher.config import Settings
from tests.fakes import FakeAnthropic, FakeAPIError, FakeUsage

SCHEMA = {"type": "object", "properties": {"make": {"type": ["string", "null"]}}}


def _client(fake, **overrides) -> AIClient:
    return AIClient(Settings(**overrides), client=fake)


async def _extract(client: AIClient):
    return await client.extract_structured(
        model=HAIKU,
        cached_system="SYSTEM",
        user_text="TITLE: VW Golf",
        tool_name="extract_listing",
        tool_schema=SCHEMA,
    )


async def test_extract_returns_tool_input_and_usage():
    fake = FakeAnthropic({"make": "Volkswagen"}, usage=FakeUsage(1000, 200))
    result = await _extract(_client(fake))
    assert result.data == {"make": "Volkswagen"}
    assert result.usage.input_tokens == 1000
    assert result.cost_usd > 0  # 1000*1 + 200*5 per MTok


async def test_system_prompt_is_cached():
    fake = FakeAnthropic({"make": "BMW"})
    await _extract(_client(fake))
    system = fake.messages.last_kwargs["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert fake.messages.last_kwargs["tool_choice"]["name"] == "extract_listing"


async def test_disabled_raises():
    fake = FakeAnthropic({"make": "BMW"})
    client = AIClient(Settings(ai_disabled=True), client=fake)
    assert client.enabled is False
    with pytest.raises(AIDisabledError):
        await _extract(client)


async def test_retries_then_succeeds(monkeypatch):
    import carcatcher.ai.client as mod

    async def _no_sleep(_):
        return None

    monkeypatch.setattr(mod.asyncio, "sleep", _no_sleep)
    fake = FakeAnthropic({"make": "Audi"}, exc_sequence=[FakeAPIError(503), None])
    result = await _extract(_client(fake))
    assert result.data == {"make": "Audi"}
    assert fake.messages.calls == 2


async def test_non_retryable_raises(monkeypatch):
    import carcatcher.ai.client as mod

    async def _no_sleep(_):
        return None

    monkeypatch.setattr(mod.asyncio, "sleep", _no_sleep)
    fake = FakeAnthropic({"make": "Audi"}, exc_sequence=[FakeAPIError(400)])
    with pytest.raises(FakeAPIError):
        await _extract(_client(fake))
    assert fake.messages.calls == 1
