"""Local Ollama client (OpenAI-compatible) for the normalization/extractor step.

Drop-in replacement for the subset of ``AIClient`` that ``Extractor`` needs:
exposes ``enabled`` and ``extract_structured(...) -> StructuredResult``. Runs the
categorization fully offline against a local Ollama model, selected by config.

Structured output uses the OpenAI-compatible ``response_format={"type":
"json_object"}``. Grammar-constrained ``json_schema`` mode is intentionally NOT
used: on small local hardware it stalls/ReadTimeouts on a schema this size. Instead
the exact field names and enum literals are derived from the same tool schema and
injected into the prompt, and enum-typed fields are lower-cased before validation —
so fuel/transmission/seller_type survive ``NormalizedListing`` instead of being
nulled by a wrong-case value. Cost is always $0 for local inference.
"""

from __future__ import annotations

import json
import logging

import httpx

from carcatcher.ai.client import AIDisabledError, StructuredResult
from carcatcher.ai.models import Usage
from carcatcher.config import Settings, get_settings

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 180.0
_DEFAULT_MAX_TOKENS = 512  # bound generation so a rambling reply can't hang the batch
_RETRIES = 1  # one extra attempt on a transient timeout


class OllamaError(RuntimeError):
    """Raised when the local Ollama endpoint fails or returns unusable output."""


class OllamaClient:
    """Minimal local-LLM client matching the ``Extractor`` contract."""

    def __init__(self, settings: Settings | None = None, *, client=None) -> None:
        self._s = settings or get_settings()
        self._client = client  # injectable httpx.AsyncClient (or test double)

    @property
    def enabled(self) -> bool:
        if self._s.ai_disabled:
            return False
        return self._s.ai_provider == "ollama"

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)
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
        """Run one structured-output completion against the local Ollama model."""
        if not self.enabled:
            raise AIDisabledError("AI is disabled or ai_provider is not 'ollama'")

        ollama_model = self._s.ollama_model or model
        url = f"{self._s.ollama_base_url.rstrip('/')}/chat/completions"
        system = cached_system + "\n\n" + _json_instruction(tool_schema)
        payload: dict = {
            "model": ollama_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens or _DEFAULT_MAX_TOKENS,
        }

        client = self._get_client()
        body = await self._post_with_retry(client, url, payload)
        data = _normalize_enums(_parse_content(body), tool_schema)
        usage = _parse_usage(body)
        return StructuredResult(data=data, usage=usage, model=ollama_model)

    async def _post_with_retry(self, client, url: str, payload: dict) -> dict:
        """POST with one retry on a transient timeout; other HTTP errors fail fast."""
        for attempt in range(_RETRIES + 1):
            try:
                resp = await client.post(
                    url, json=payload, headers={"Authorization": "Bearer ollama"}
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.TimeoutException as exc:
                if attempt < _RETRIES:
                    logger.warning("Ollama timeout (%s), retrying once", url)
                    continue
                raise OllamaError(f"Ollama request to {url} timed out") from exc
            except httpx.HTTPError as exc:
                logger.warning("Ollama request failed (%s): %s", url, exc)
                raise OllamaError(f"Ollama request to {url} failed: {exc}") from exc
        raise OllamaError(f"Ollama request to {url} failed")  # pragma: no cover


def _enum_fields(tool_schema: dict) -> dict[str, list[str]]:
    """Map each enum-typed property to its allowed (non-null) literals."""
    props = tool_schema.get("properties", {})
    return {
        name: [v for v in spec["enum"] if v is not None]
        for name, spec in props.items()
        if isinstance(spec, dict) and "enum" in spec
    }


def _json_instruction(tool_schema: dict) -> str:
    """Prompt suffix that pins the JSON keys + enum literals (no grammar needed)."""
    keys = list(tool_schema.get("properties", {}).keys())
    lines = [
        "Respond with ONLY a single JSON object and nothing else (no prose, no "
        "markdown). Use EXACTLY these keys, with null when a value is not clearly "
        "stated:",
        ", ".join(keys) + ".",
    ]
    enums = _enum_fields(tool_schema)
    if enums:
        lines.append("For these fields use ONLY one of the listed lowercase values:")
        lines += [f"- {name}: {' | '.join(vals)}" for name, vals in enums.items()]
    return "\n".join(lines)


def _normalize_enums(data: dict, tool_schema: dict) -> dict:
    """Lower-case enum-typed string values so correct-but-wrong-case values (e.g.
    'Automatic', 'Private') survive NormalizedListing validation instead of nulling."""
    out = dict(data)
    for name in _enum_fields(tool_schema):
        value = out.get(name)
        if isinstance(value, str):
            out[name] = value.strip().lower()
    return out


def _parse_content(body: dict) -> dict:
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OllamaError(f"unexpected Ollama response shape: {body!r}") from exc
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise OllamaError(f"Ollama content was not valid JSON: {content!r}") from exc
    if not isinstance(parsed, dict):
        raise OllamaError(f"Ollama content was not a JSON object: {parsed!r}")
    return parsed


def _parse_usage(body: dict) -> Usage:
    usage = body.get("usage") or {}
    return Usage(
        input_tokens=int(usage.get("prompt_tokens", 0) or 0),
        output_tokens=int(usage.get("completion_tokens", 0) or 0),
    )
