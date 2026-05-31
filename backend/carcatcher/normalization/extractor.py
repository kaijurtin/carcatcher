"""Haiku-based normalization: messy listing text -> NormalizedListing."""

from __future__ import annotations

from carcatcher.ai.client import AIClient, StructuredResult
from carcatcher.ai.models import HAIKU
from carcatcher.normalization.prompts import NORMALIZATION_SYSTEM
from carcatcher.normalization.schema import NORMALIZED_TOOL_SCHEMA, NormalizedListing

TOOL_NAME = "extract_listing"


def _build_user_text(raw_title: str, raw_text: str) -> str:
    parts = []
    if raw_title:
        parts.append(f"TITLE: {raw_title}")
    if raw_text:
        parts.append(f"DESCRIPTION:\n{raw_text}")
    return "\n\n".join(parts) if parts else "(empty listing)"


class Extractor:
    """Wraps an AIClient to normalize one listing at a time."""

    def __init__(self, ai: AIClient) -> None:
        self._ai = ai

    @property
    def enabled(self) -> bool:
        return self._ai.enabled

    async def extract(
        self, raw_title: str, raw_text: str
    ) -> tuple[NormalizedListing, StructuredResult]:
        result = await self._ai.extract_structured(
            model=HAIKU,
            cached_system=NORMALIZATION_SYSTEM,
            user_text=_build_user_text(raw_title, raw_text),
            tool_name=TOOL_NAME,
            tool_schema=NORMALIZED_TOOL_SCHEMA,
            tool_description="Extract the structured car attributes from the listing.",
        )
        normalized = NormalizedListing.model_validate(result.data)
        return normalized, result
