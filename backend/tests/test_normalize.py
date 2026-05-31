"""Normalize pipeline tests: application, idempotency, fill-if-missing, AI off."""

from __future__ import annotations

from sqlmodel import Session, select

from carcatcher.ai.client import AIClient
from carcatcher.config import Settings
from carcatcher.db.engine import get_engine
from carcatcher.db.models import Listing
from carcatcher.normalization.extractor import Extractor
from carcatcher.pipeline.normalize import normalize_pending
from tests.fakes import FakeAnthropic


def _extractor(tool_input: dict, **settings) -> Extractor:
    ai = AIClient(Settings(**settings), client=FakeAnthropic(tool_input))
    return Extractor(ai)


def _seed(session: Session, **over) -> Listing:
    base = dict(
        source="kleinanzeigen", source_id="1", url="u1",
        raw_title="VW Golf 1.6", raw_text="Benziner, Schaltgetriebe",
    )
    base.update(over)
    listing = Listing(**base)
    session.add(listing)
    session.commit()
    session.refresh(listing)
    return listing


async def test_normalizes_pending_and_sets_fields(test_engine):
    ex = _extractor({"make": "Volkswagen", "model": "Golf", "fuel": "petrol"})
    with Session(get_engine()) as s:
        _seed(s)
        stats = await normalize_pending(s, ex)
        assert stats.normalized == 1
        assert stats.cost_usd > 0
        row = s.exec(select(Listing)).one()
        assert row.make == "Volkswagen"
        assert row.fuel == "petrol"
        assert row.normalized_at is not None


async def test_idempotent_second_run_is_noop(test_engine):
    ex = _extractor({"make": "Volkswagen"})
    with Session(get_engine()) as s:
        _seed(s)
        await normalize_pending(s, ex)
        again = await normalize_pending(s, ex)
        assert again.normalized == 0  # already normalized -> not pending


async def test_card_price_not_overwritten_but_fills_year(test_engine):
    # Card gave price=4300; Haiku returns a different price + a year card lacked.
    ex = _extractor({"make": "VW", "price": 9999, "year": 2005})
    with Session(get_engine()) as s:
        _seed(s, price=4300, year=None)
        await normalize_pending(s, ex)
        row = s.exec(select(Listing)).one()
        assert row.price == 4300  # card value preserved
        assert row.year == 2005   # filled because missing


async def test_skipped_when_ai_disabled(test_engine):
    ex = _extractor({"make": "VW"}, ai_disabled=True)
    with Session(get_engine()) as s:
        _seed(s)
        stats = await normalize_pending(s, ex)
        assert stats.skipped is True
        row = s.exec(select(Listing)).one()
        assert row.make is None  # untouched; aggregation still works


async def test_failure_records_error_and_marks_attempted(test_engine):
    # FakeAnthropic returns a tool input; force a failure by breaking validation.
    class Boom(Extractor):
        async def extract(self, *a, **k):
            raise RuntimeError("haiku exploded")

    ai = AIClient(Settings(), client=FakeAnthropic({"make": "x"}))
    ex = Boom(ai)
    with Session(get_engine()) as s:
        _seed(s)
        stats = await normalize_pending(s, ex)
        assert stats.failed == 1
        row = s.exec(select(Listing)).one()
        assert row.normalization_error and "exploded" in row.normalization_error
        assert row.normalized_at is not None  # marked attempted
