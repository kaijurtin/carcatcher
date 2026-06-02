"""Guide generator: fresh render, source citation, and additive enhance mode."""

from __future__ import annotations

from carcatcher.ai.models import Usage
from carcatcher.research.guide_generator import generate_guide


class _FakeFirecrawl:
    """Canned search/scrape doubles — no network."""

    async def search(self, query: str, *, limit: int = 6) -> list[dict]:
        return [
            {"url": "https://www.goingelectric.de/test", "title": "GoingElectric",
             "description": "Test"},
            {"url": "https://example.com/other", "title": "Other", "description": "x"},
        ]

    async def scrape(self, url: str, *, formats=None, only_main_content=True) -> dict:
        return {"markdown": f"# Scraped {url}\nVarianten: Pro, Pro S. 77 kWh."}


class _FakeResult:
    def __init__(self, data: dict) -> None:
        self.data = data
        self.usage = Usage(input_tokens=10, output_tokens=20)
        self.cost_usd = 0.0


class _FakeProvider:
    def __init__(self, data: dict) -> None:
        self._data = data

    async def extract_structured(self, **kwargs) -> _FakeResult:
        return _FakeResult(self._data)


_AI_DATA = {
    "overview": "Solides Elektro-SUV für Familien.",
    "variants": ["Pro 77 kWh", "Pro S 82 kWh"],
    "battery_suppliers": "LG Energy Solution, SK On",
    "problems": ["Software-Bugs frühe Baujahre"],
    "recalls": ["KBA-Rückruf Aktionscode 12345"],
    "buying_tips": ["MEB-Update prüfen"],
    "best_year": "2023",
    "year_range": "2020–2026",
    "sources": [{"title": "GoingElectric", "url": "https://www.goingelectric.de/test"}],
}


async def test_generate_guide_fresh_has_sections_and_front_matter():
    md = await generate_guide(
        "Volkswagen", "ID.4",
        provider=_FakeProvider(_AI_DATA), firecrawl=_FakeFirecrawl(),
    )
    # Front-matter
    assert md.startswith("---")
    assert "make: Volkswagen" in md
    assert "model: ID.4" in md
    assert "market: Germany" in md
    assert "revisions: 1" in md
    # Section headings (TEMPLATE shape)
    assert "## Variants & specs" in md
    assert "## Battery cell suppliers" in md
    assert "## Known problems & recalls" in md
    assert "## Buying tips — best year" in md
    assert "## Sources" in md
    assert "## Revision log" in md
    # Content + source citation
    assert "Pro S 82 kWh" in md
    assert "KBA-Rückruf" in md
    assert "https://www.goingelectric.de/test" in md
    assert "Bestes Baujahr: 2023" in md


async def test_generate_guide_enhance_preserves_existing_and_bumps_revision():
    existing = (
        "---\n"
        "make: Volkswagen\nmodel: ID.4\nmarket: Germany (DE)\n"
        "year_range: 2020–2026\nupdated: 2026-01-01\nrevisions: 2\nsources: 3\n"
        "---\n"
        "# Volkswagen ID.4 — Kaufberatung (DE)\n\n"
        "ORIGINAL_UNIQUE_PARAGRAPH that must survive enhancement.\n"
    )
    md = await generate_guide(
        "Volkswagen", "ID.4",
        provider=_FakeProvider(_AI_DATA), firecrawl=_FakeFirecrawl(),
        existing_md=existing,
    )
    # Prior body preserved verbatim.
    assert "ORIGINAL_UNIQUE_PARAGRAPH that must survive enhancement." in md
    # Revisions bumped 2 -> 3.
    assert "revisions: 3" in md
    # New findings appended under a dated update heading.
    assert "## Update" in md
    assert "Pro S 82 kWh" in md


async def test_generate_guide_resilient_when_no_sources():
    class _EmptyFirecrawl:
        async def search(self, query, *, limit=6):
            return []

        async def scrape(self, url, *, formats=None, only_main_content=True):
            raise RuntimeError("should not be called")

    md = await generate_guide(
        "Tesla", "Model 3",
        provider=_FakeProvider({}), firecrawl=_EmptyFirecrawl(),
    )
    assert md.startswith("---")
    assert "make: Tesla" in md
    assert "## Sources" in md  # still renders a valid guide
