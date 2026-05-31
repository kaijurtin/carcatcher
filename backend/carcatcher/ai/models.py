"""Claude model tiers, pricing, and cost estimation.

Tiering (cost control): Haiku does the high-volume normalization, Sonnet the
per-listing evaluation (P5), Opus the rare cross-candidate recommendation (P8).
"""

from __future__ import annotations

from dataclasses import dataclass

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
OPUS = "claude-opus-4-8"


@dataclass(frozen=True)
class ModelSpec:
    model: str
    max_tokens: int
    # USD per million tokens (approximate; used only for the budget soft-guard).
    input_per_mtok: float
    output_per_mtok: float


SPECS: dict[str, ModelSpec] = {
    HAIKU: ModelSpec(HAIKU, max_tokens=1024, input_per_mtok=1.0, output_per_mtok=5.0),
    SONNET: ModelSpec(SONNET, max_tokens=1536, input_per_mtok=3.0, output_per_mtok=15.0),
    OPUS: ModelSpec(OPUS, max_tokens=2048, input_per_mtok=15.0, output_per_mtok=75.0),
}


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


def estimate_cost(model: str, usage: Usage) -> float:
    """Conservative USD estimate (ignores cache discounts, so never under-reports)."""
    spec = SPECS.get(model)
    if spec is None:
        return 0.0
    return (
        usage.input_tokens * spec.input_per_mtok
        + usage.output_tokens * spec.output_per_mtok
    ) / 1_000_000
