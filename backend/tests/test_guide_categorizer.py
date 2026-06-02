"""Tests for the guide-aware VW ID variant categorizer: guide loading, ambiguity
detection, non-destructive apply, the Haiku agent (mocked), and the pipeline step."""

from __future__ import annotations

from sqlmodel import Session

from carcatcher.ai.client import AIClient
from carcatcher.ai.models import HAIKU
from carcatcher.config import Settings
from carcatcher.db.engine import get_engine
from carcatcher.db.models import Listing
from carcatcher.normalization.guide_categorizer import (
    AgentVariant,
    GuideCategorizer,
    apply_agent_variant,
    is_ambiguous_vw_id,
)
from carcatcher.normalization.guide_loader import load_guide_knowledge
from carcatcher.pipeline.categorize import agent_categorize_active
from tests.fakes import FakeAnthropic


def _listing(**kw) -> Listing:
    base = dict(source="kleinanzeigen", source_id="x", url="x", raw_title="")
    base.update(kw)
    return Listing(**base)


def _agent(tool_input: dict) -> GuideCategorizer:
    ai = AIClient(
        Settings(ai_disabled=False),
        client=FakeAnthropic(tool_input, tool_name="categorize_variant"),
    )
    return GuideCategorizer(ai)


# --- guide loader ---------------------------------------------------------- #

def test_load_guide_knowledge_returns_variants_and_year():
    kn = load_guide_knowledge("Volkswagen", "ID.4")
    assert kn is not None
    assert kn.model == "ID.4"
    assert kn.year_range  # frontmatter year_range present
    # The bundled ID.4 guide's Variants & specs section names these trims.
    assert "Pro" in kn.variants_section
    assert "GTX" in kn.variants_section


def test_load_guide_knowledge_missing_returns_none():
    assert load_guide_knowledge("Tesla", "Model 3") is None


# --- ambiguity detection --------------------------------------------------- #

def test_ambiguous_for_vw_id_without_variant():
    li = _listing(make="Volkswagen", model="ID.4", variant=None,
                  raw_title="VW ID.4 Klima Navi", year=2023)
    assert is_ambiguous_vw_id(li) is True


def test_not_ambiguous_when_variant_already_set():
    li = _listing(make="Volkswagen", model="ID.4", variant="Pro",
                  raw_title="VW ID.4 Pro", year=2023)
    assert is_ambiguous_vw_id(li) is False


def test_not_ambiguous_when_model_locked():
    li = _listing(make="Volkswagen", model="ID.4", variant=None,
                  raw_title="VW ID.4", year=2023, model_locked=True)
    assert is_ambiguous_vw_id(li) is False


def test_not_ambiguous_for_non_vw_id():
    li = _listing(make="Volkswagen", model="Golf", variant=None,
                  raw_title="VW Golf", year=2020)
    assert is_ambiguous_vw_id(li) is False


# --- non-destructive apply ------------------------------------------------- #

def test_apply_fills_empty_variant_and_battery():
    li = _listing(make="Volkswagen", model="ID.4", variant=None, battery_kwh=None)
    changed = apply_agent_variant(li, AgentVariant(variant="GTX", battery_kwh=77.0))
    assert changed is True
    assert (li.variant, li.battery_kwh) == ("GTX", 77.0)


def test_apply_does_not_clobber_existing_variant():
    li = _listing(make="Volkswagen", model="ID.4", variant="Pro", battery_kwh=77.0)
    changed = apply_agent_variant(li, AgentVariant(variant="GTX", battery_kwh=79.0))
    assert changed is False
    assert (li.variant, li.battery_kwh) == ("Pro", 77.0)


def test_apply_no_op_when_model_locked():
    li = _listing(make="Volkswagen", model="ID.4", variant=None, model_locked=True)
    assert apply_agent_variant(li, AgentVariant(variant="GTX")) is False
    assert li.variant is None


# --- the agent (mocked Haiku) ---------------------------------------------- #

async def test_agent_picks_variant_from_guide():
    cat = _agent({"variant": "GTX", "battery_kwh": 77.0, "confidence": "high"})
    kn = load_guide_knowledge("Volkswagen", "ID.4")
    assert kn is not None
    li = _listing(make="Volkswagen", model="ID.4", variant=None, year=2023,
                  raw_title="VW ID.4 4MOTION Allrad 220 kW")
    result, struct = await cat.categorize(li, kn)
    assert result.variant == "GTX"
    assert result.battery_kwh == 77.0
    assert result.confidence == "high"
    # Routed through Haiku with the variant tool.
    kwargs = cat._ai._client.messages.last_kwargs  # type: ignore[union-attr]
    assert kwargs["model"] == HAIKU
    assert kwargs["tool_choice"]["name"] == "categorize_variant"
    assert struct.cost_usd > 0


async def test_agent_returns_null_variant_unchanged():
    cat = _agent({"variant": None, "confidence": "low"})
    kn = load_guide_knowledge("Volkswagen", "ID.4")
    assert kn is not None
    li = _listing(make="Volkswagen", model="ID.4", variant=None, year=2021,
                  raw_title="VW ID.4 Elektro")
    result, _ = await cat.categorize(li, kn)
    assert result.variant is None


# --- pipeline step --------------------------------------------------------- #

async def test_agent_categorize_active_resolves_ambiguous(test_engine):
    with Session(get_engine()) as session:
        li = _listing(source_id="1", make="Volkswagen", model="ID.4", variant=None,
                      year=2023, fuel="electric", raw_title="VW ID.4 Klima Navi",
                      status="active")
        session.add(li)
        session.commit()
        session.refresh(li)
        lid = li.id

    cat = _agent({"variant": "GTX", "battery_kwh": 77.0, "confidence": "high"})
    with Session(get_engine()) as session:
        stats = await agent_categorize_active(session, cat)

    assert stats.resolved == 1
    assert stats.haiku_calls == 1
    with Session(get_engine()) as session:
        li = session.get(Listing, lid)
        assert li.variant == "GTX"
        assert li.battery_kwh == 77.0


async def test_agent_categorize_active_skipped_when_disabled(test_engine):
    cat = GuideCategorizer(AIClient(Settings(ai_disabled=True)))  # enabled == False
    with Session(get_engine()) as session:
        stats = await agent_categorize_active(session, cat)
    assert stats.skipped is True
    assert stats.haiku_calls == 0
