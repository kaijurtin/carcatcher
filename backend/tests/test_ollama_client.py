"""Local Ollama client + provider selection in build_state."""

from __future__ import annotations

import json

import pytest

from carcatcher.ai.client import AIClient, AIDisabledError
from carcatcher.ai.models import OPUS, SONNET
from carcatcher.ai.ollama_client import OllamaClient
from carcatcher.app_state import build_state
from carcatcher.config import Settings
from carcatcher.normalization.schema import NORMALIZED_TOOL_SCHEMA, NormalizedListing


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:  # pragma: no cover - trivial
        return None

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """Captures the request and returns a canned chat-completions response."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.last_call: dict | None = None

    async def post(self, url, *, json=None, headers=None):
        self.last_call = {"url": url, "json": json, "headers": headers}
        return _FakeResponse(self._payload)


def _ollama_settings(**overrides) -> Settings:
    base = dict(
        scheduler_enabled=False,
        ai_disabled=False,
        ai_provider="ollama",
        scrape_min_interval_ms=0,
    )
    base.update(overrides)
    return Settings(**base)


def _chat_completion(content: dict, usage: dict | None = None) -> dict:
    body: dict = {"choices": [{"message": {"content": json.dumps(content)}}]}
    if usage is not None:
        body["usage"] = usage
    return body


async def test_extract_structured_preserves_enum_fields():
    # Arrange: WRONG-CASE enums, as a json_object model emits. The client lower-cases
    # enum fields so they survive validation instead of being nulled.
    content = {
        "make": "Tesla",
        "model": "Model 3",
        "fuel": "Electric",
        "transmission": "Automatic",
        "seller_type": "Private",
        "battery_kwh": 77,
    }
    fake = _FakeAsyncClient(
        _chat_completion(content, usage={"prompt_tokens": 120, "completion_tokens": 40})
    )
    ollama = OllamaClient(_ollama_settings(ollama_model="qwen2.5:3b"), client=fake)

    # Act
    result = await ollama.extract_structured(
        model="claude-haiku-4-5-20251001",
        cached_system="system prompt",
        user_text="TITLE: Tesla Model 3",
        tool_name="extract_listing",
        tool_schema=NORMALIZED_TOOL_SCHEMA,
    )

    # Assert: enum fields are lower-cased and NOT nulled by validation.
    normalized = NormalizedListing.model_validate(result.data)
    assert normalized.fuel == "electric"
    assert normalized.transmission == "automatic"
    assert normalized.seller_type == "private"
    assert normalized.battery_kwh == 77
    assert result.cost_usd == 0.0
    assert result.model == "qwen2.5:3b"
    assert result.usage.input_tokens == 120
    assert result.usage.output_tokens == 40


async def test_extract_structured_request_uses_json_object_and_pins_keys():
    fake = _FakeAsyncClient(_chat_completion({"make": "VW"}))
    ollama = OllamaClient(_ollama_settings(ollama_model="qwen2.5:3b"), client=fake)

    await ollama.extract_structured(
        model="claude-haiku-4-5-20251001",
        cached_system="sys",
        user_text="text",
        tool_name="extract_listing",
        tool_schema=NORMALIZED_TOOL_SCHEMA,
    )

    sent = fake.last_call
    assert sent is not None
    assert sent["url"].endswith("/v1/chat/completions")
    assert sent["json"]["model"] == "qwen2.5:3b"  # ignores the Anthropic model arg
    assert sent["json"]["temperature"] == 0
    # json_object mode (json_schema/grammar stalls on small local hardware).
    assert sent["json"]["response_format"] == {"type": "json_object"}
    # Schema-derived keys + enum literals are injected into the system prompt.
    system_msg = sent["json"]["messages"][0]["content"]
    assert "battery_kwh" in system_msg and "seller_type" in system_msg
    assert "private" in system_msg and "automatic" in system_msg


async def test_extract_structured_raises_when_disabled():
    fake = _FakeAsyncClient(_chat_completion({}))
    ollama = OllamaClient(
        _ollama_settings(ai_provider="anthropic"), client=fake
    )
    with pytest.raises(AIDisabledError):
        await ollama.extract_structured(
            model="m",
            cached_system="s",
            user_text="u",
            tool_name="t",
            tool_schema={},
        )


def test_enabled_true_only_for_ollama_provider_and_not_disabled():
    assert OllamaClient(_ollama_settings()).enabled is True
    assert OllamaClient(_ollama_settings(ai_disabled=True)).enabled is False
    assert OllamaClient(_ollama_settings(ai_provider="anthropic")).enabled is False


def test_build_state_uses_ollama_for_all_roles():
    settings = _ollama_settings()
    state = build_state(settings)

    # All four AI roles run locally; AIClient is still built but unused.
    assert isinstance(state.ai, AIClient)
    for role in (state.extractor, state.evaluator, state.translator, state.recommender):
        assert isinstance(role._ai, OllamaClient)


def test_build_state_uses_anthropic_for_all_roles_by_default():
    settings = Settings(
        scheduler_enabled=False, ai_disabled=False, scrape_min_interval_ms=0,
    )
    state = build_state(settings)
    for role in (state.extractor, state.evaluator, state.translator, state.recommender):
        assert role._ai is state.ai


async def test_max_tokens_sized_by_role_tier():
    # The role passes its Anthropic model id; OllamaClient sizes the budget from SPECS.
    for model, expected in [(SONNET, 1536), (OPUS, 2048)]:
        fake = _FakeAsyncClient(_chat_completion({"make": "VW"}))
        ollama = OllamaClient(_ollama_settings(), client=fake)
        await ollama.extract_structured(
            model=model, cached_system="s", user_text="u",
            tool_name="t", tool_schema=NORMALIZED_TOOL_SCHEMA,
        )
        assert fake.last_call["json"]["max_tokens"] == expected
