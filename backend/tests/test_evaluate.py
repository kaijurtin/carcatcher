"""Sonnet evaluation tests: candidate selection, evaluator, pipeline, force-eval API."""

from __future__ import annotations

from sqlmodel import Session, select

from carcatcher.ai.client import AIClient
from carcatcher.ai.evaluate import Evaluator, build_eval_input
from carcatcher.config import Settings
from carcatcher.db.engine import get_engine
from carcatcher.db.models import Listing, ListingStatus, Shortlist, ShortlistItem
from carcatcher.pipeline.evaluate import evaluate_candidates, evaluate_one
from carcatcher.scoring.candidates import select_candidates
from tests.fakes import FakeAnthropic

EVAL = {
    "summary": "Solid daily driver, priced under market.",
    "pros": ["TÜV neu", "One owner"],
    "cons": ["High mileage"],
    "red_flags": [],
    "deal_verdict": "good",
    "confidence": "high",
}


def _evaluator(tool_input=EVAL, **settings) -> Evaluator:
    ai = AIClient(Settings(**settings), client=FakeAnthropic(tool_input, tool_name="record_evaluation"))
    return Evaluator(ai)


def _listing(sid: str, **over) -> Listing:
    base = dict(
        source="kleinanzeigen", source_id=sid, url=f"u{sid}",
        make="Volkswagen", model="Golf", price=9000, mileage_km=100000, year=2015,
        deal_score=0.15, comp_count=6, status=ListingStatus.ACTIVE.value,
    )
    base.update(over)
    return Listing(**base)


# --- candidate selection ---------------------------------------------------- #
def test_select_candidates_deal_and_shortlist(test_engine):
    s = Settings(deal_threshold=0.08, min_comps=5, max_sonnet_evals_per_run=30)
    with Session(get_engine()) as sess:
        good = _listing("good", deal_score=0.20)
        weak = _listing("weak", deal_score=0.02)          # below threshold
        few = _listing("few", deal_score=0.20, comp_count=2)  # too few comps
        shortlisted = _listing("sl", deal_score=None, comp_count=0)  # only via shortlist
        sess.add_all([good, weak, few, shortlisted])
        sess.commit()
        sl = Shortlist(name="default")
        sess.add(sl)
        sess.commit()
        sess.add(ShortlistItem(shortlist_id=sl.id, listing_id=shortlisted.id))
        sess.commit()

        ids = {c.source_id for c in select_candidates(sess, s)}
        assert ids == {"good", "sl"}


def test_select_candidates_skips_already_evaluated(test_engine):
    from carcatcher.db.models import utcnow

    s = Settings(deal_threshold=0.08, min_comps=5)
    with Session(get_engine()) as sess:
        sess.add(_listing("done", deal_score=0.2, ai_evaluated_at=utcnow()))
        sess.commit()
        assert select_candidates(sess, s) == []


def test_select_candidates_caps(test_engine):
    s = Settings(deal_threshold=0.08, min_comps=5, max_sonnet_evals_per_run=2)
    with Session(get_engine()) as sess:
        sess.add_all([_listing(str(i), deal_score=0.1 + i / 100) for i in range(5)])
        sess.commit()
        picked = select_candidates(sess, s)
        assert len(picked) == 2
        # Highest deal_score first.
        assert picked[0].deal_score >= picked[1].deal_score


# --- evaluator + input ------------------------------------------------------ #
def test_build_eval_input_includes_price_and_fair():
    listing = _listing("x", price=9000, fair_price_estimate=10500, comp_count=6,
                        raw_text="TÜV neu, scheckheftgepflegt")
    text = build_eval_input(listing)
    assert "9.000 EUR" in text
    assert "10.500 EUR" in text
    assert "scheckheft" in text


async def test_evaluator_returns_evaluation():
    ev = _evaluator()
    listing = _listing("x")
    evaluation, result = await ev.evaluate(listing)
    assert evaluation["deal_verdict"] == "good"
    assert result.cost_usd > 0


# --- pipeline --------------------------------------------------------------- #
async def test_evaluate_candidates_applies_and_counts(test_engine):
    ev = _evaluator()
    with Session(get_engine()) as sess:
        sess.add(_listing("good", deal_score=0.2))
        sess.commit()
        stats = await evaluate_candidates(sess, ev)
        assert stats.evaluated == 1
        assert stats.sonnet_calls == 1
        row = sess.exec(select(Listing)).one()
        assert row.ai_evaluation["deal_verdict"] == "good"
        assert row.ai_evaluated_at is not None


async def test_evaluate_candidates_skipped_when_disabled(test_engine):
    ev = _evaluator(ai_disabled=True)
    with Session(get_engine()) as sess:
        sess.add(_listing("good", deal_score=0.2))
        sess.commit()
        stats = await evaluate_candidates(sess, ev)
        assert stats.skipped is True


async def test_evaluate_one_forces(test_engine):
    ev = _evaluator()
    with Session(get_engine()) as sess:
        weak = _listing("weak", deal_score=0.0)  # not a candidate, but forced
        sess.add(weak)
        sess.commit()
        evaluation = await evaluate_one(sess, ev, weak)
        assert evaluation["deal_verdict"] == "good"
        assert weak.ai_evaluated_at is not None


# --- force-eval API --------------------------------------------------------- #
def test_force_eval_404(client):
    assert client.post("/api/listings/999/evaluate").status_code == 404


def test_force_eval_409_when_ai_disabled(client):
    # The TestClient lifespan builds state with AI disabled (test settings).
    with Session(get_engine()) as sess:
        sess.add(_listing("x"))
        sess.commit()
    resp = client.post("/api/listings/1/evaluate")
    assert resp.status_code == 409
