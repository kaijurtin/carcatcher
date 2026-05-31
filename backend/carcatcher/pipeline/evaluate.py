"""Evaluate step: run Sonnet on the selected candidates (cost-capped)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlmodel import Session

from carcatcher.ai.evaluate import Evaluator
from carcatcher.config import get_settings
from carcatcher.db.models import Listing, utcnow
from carcatcher.scoring.candidates import select_candidates

_SONNET_CONCURRENCY = 3


@dataclass
class EvalStats:
    evaluated: int = 0
    failed: int = 0
    skipped: bool = False
    sonnet_calls: int = 0
    cost_usd: float = 0.0


def apply_evaluation(listing: Listing, evaluation: dict) -> None:
    listing.ai_evaluation = evaluation
    listing.ai_evaluated_at = utcnow()


async def evaluate_candidates(session: Session, evaluator: Evaluator) -> EvalStats:
    """Evaluate baseline-passing / shortlisted listings. No-op if AI disabled."""
    stats = EvalStats()
    if not evaluator.enabled:
        stats.skipped = True
        return stats

    settings = get_settings()
    candidates = select_candidates(session, settings)
    if not candidates:
        return stats

    sem = asyncio.Semaphore(_SONNET_CONCURRENCY)

    async def work(listing: Listing):
        async with sem:
            try:
                evaluation, result = await evaluator.evaluate(listing)
                return listing, evaluation, result, None
            except Exception as exc:  # noqa: BLE001 — recorded per-listing
                return listing, None, None, exc

    results = await asyncio.gather(*(work(li) for li in candidates))

    for listing, evaluation, result, error in results:
        if error is not None or evaluation is None:
            stats.failed += 1
            continue
        apply_evaluation(listing, evaluation)
        stats.evaluated += 1
        stats.sonnet_calls += 1
        stats.cost_usd += result.cost_usd
        session.add(listing)

    session.commit()
    return stats


async def evaluate_one(session: Session, evaluator: Evaluator, listing: Listing) -> dict:
    """Force-evaluate a single listing on demand. Returns the evaluation dict."""
    evaluation, _ = await evaluator.evaluate(listing)
    apply_evaluation(listing, evaluation)
    session.add(listing)
    session.commit()
    return evaluation
