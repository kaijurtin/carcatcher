"""P8 tests: NL translator, Opus recommender, and their endpoints."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from carcatcher.ai.client import AIClient
from carcatcher.ai.nl_search import Translator
from carcatcher.ai.recommend import Recommender, build_recommend_input
from carcatcher.app_state import AppState, set_state
from carcatcher.config import Settings
from carcatcher.db.engine import get_engine
from carcatcher.db.models import Listing, ListingStatus
from carcatcher.queries import search_listings
from carcatcher.schemas import StructuredFilters
from tests.fakes import FakeAnthropic


def _listing(sid: str, **over) -> Listing:
    base = dict(
        source="kleinanzeigen", source_id=sid, url=f"u{sid}",
        make="Volkswagen", model="Golf", price=9000, mileage_km=100000, year=2015,
        deal_score=0.1, comp_count=6, status=ListingStatus.ACTIVE.value,
    )
    base.update(over)
    return Listing(**base)


# --- queries ---------------------------------------------------------------- #
def test_search_listings_applies_filters(test_engine):
    with Session(get_engine()) as s:
        s.add_all([
            _listing("1", make="Volkswagen", model="Golf", price=4000),
            _listing("2", make="BMW", model="3er", price=12000),
        ])
        s.commit()
        out = search_listings(s, StructuredFilters(make="Volkswagen", price_max=5000))
        assert [li.source_id for li in out] == ["1"]


# --- translator ------------------------------------------------------------- #
async def test_translator_returns_filters():
    payload = {
        "filters": {"make": "Volkswagen", "price_max": 8000, "fuel": "diesel"},
        "ranking": [{"field": "deal_score", "direction": "desc"}],
        "rationale": "Cheap diesel Golf, best value first.",
    }
    ai = AIClient(Settings(), client=FakeAnthropic(payload, tool_name="build_search"))
    data, result = await Translator(ai).translate("günstiger diesel golf")
    assert data["filters"]["make"] == "Volkswagen"
    assert result.cost_usd > 0


# --- recommender ------------------------------------------------------------ #
def test_build_recommend_input_includes_ids_and_verdicts():
    a = _listing("1", price=9000, fair_price_estimate=10000,
                 ai_evaluation={"deal_verdict": "good", "summary": "solid", "red_flags": []})
    a.id = 1
    text = build_recommend_input([a])
    assert "id=1" in text
    assert "good" in text


async def test_recommender_returns_pick():
    payload = {
        "top_pick_id": 2,
        "summary": "The BMW is the better long-term value.",
        "ranking": [{"listing_id": 2, "rank": 1, "reason": "lower risk"}],
        "caveats": ["check service history"],
    }
    ai = AIClient(Settings(), client=FakeAnthropic(payload, tool_name="record_recommendation"))
    a, b = _listing("1"), _listing("2")
    a.id, b.id = 1, 2
    data, _ = await Recommender(ai).recommend([a, b])
    assert data["top_pick_id"] == 2


# --- endpoints (AI disabled via test settings) ------------------------------ #
def test_nl_search_409_when_ai_disabled(client):
    resp = client.post("/api/search/nl", json={"query": "cheap golf"})
    assert resp.status_code == 409


def test_recommend_400_when_too_few(client):
    resp = client.post("/api/recommend", json={"listing_ids": [1]})
    assert resp.status_code == 400


def test_recommend_409_when_ai_disabled(client):
    with Session(get_engine()) as s:
        s.add_all([_listing("1"), _listing("2")])
        s.commit()
    resp = client.post("/api/recommend", json={"listing_ids": [1, 2]})
    assert resp.status_code == 409


# --- endpoints with AI enabled (inject a fake-backed state) ----------------- #
@pytest.fixture()
def ai_state(test_engine):
    """Install an AppState whose AI returns a canned NL-search payload."""
    from carcatcher.ai.evaluate import Evaluator
    from carcatcher.normalization.extractor import Extractor
    from carcatcher.scraping.firecrawl_client import FirecrawlClient

    nl_payload = {
        "filters": {"make": "Volkswagen", "price_max": 8000},
        "ranking": [{"field": "price", "direction": "asc"}],
        "rationale": "Cheapest VWs first.",
    }
    fake = FakeAnthropic(nl_payload, tool_name="build_search")
    ai = AIClient(Settings(), client=fake)
    st = AppState(
        firecrawl=FirecrawlClient(Settings()),
        scrapers={},
        ai=ai,
        extractor=Extractor(ai),
        evaluator=Evaluator(ai),
        translator=Translator(ai),
        recommender=Recommender(ai),
    )
    set_state(st)
    yield st
    set_state(None)


def test_nl_search_returns_results(client, ai_state):
    with Session(get_engine()) as s:
        s.add_all([_listing("1", price=4000), _listing("2", price=12000)])
        s.commit()
    resp = client.post("/api/search/nl", json={"query": "cheap golf under 8000"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["filters"]["make"] == "Volkswagen"
    assert body["rationale"]
    assert {li["source_id"] for li in body["results"]} == {"1"}
