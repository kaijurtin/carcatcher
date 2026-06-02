"""Generate (or enhance) a per-model buyer's guide from live web research.

Pipeline: 3 German-scoped search queries -> dedupe & prefer DE/LU/FR sources ->
scrape the top few -> truncate -> one structured AI call against GUIDE_SCHEMA ->
render the TEMPLATE markdown. Resilient end-to-end: search/scrape failures are
skipped, and with zero usable sources a minimal "limited sources" guide is still
produced rather than crashing. Enhance mode is additive — prior body is preserved.
"""

from __future__ import annotations

import logging
from datetime import date
from urllib.parse import urlparse

from carcatcher.ai.client import AIDisabledError
from carcatcher.ai.models import SONNET
from carcatcher.api.routes.models import parse_front_matter
from carcatcher.research.prompts import GUIDE_SYSTEM

logger = logging.getLogger(__name__)

# Self-contained JSON schema (no $ref) for the structured AI extraction. Every
# field is optional/nullable: the model leaves out anything not in the sources.
GUIDE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "overview": {"type": ["string", "null"]},
        "variants": {"type": "array", "items": {"type": "string"}},
        "battery_suppliers": {"type": ["string", "null"]},
        "problems": {"type": "array", "items": {"type": "string"}},
        "recalls": {"type": "array", "items": {"type": "string"}},
        "buying_tips": {"type": "array", "items": {"type": "string"}},
        "best_year": {"type": ["string", "null"]},
        "year_range": {"type": ["string", "null"]},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": ["string", "null"]},
                    "url": {"type": ["string", "null"]},
                },
            },
        },
    },
    "required": [],
}

# Domains/keywords that mark a source as German/EU-relevant (preferred over others).
_PREFERRED_HOSTS = (
    "goingelectric",
    "motor-talk",
    "adac",
    "tuev",
    "tuv",
    "autobild",
    "ecomento",
    "electrive",
    "ev-database",
    "batterydesign",
    "kba",
)
_PREFERRED_TLDS = (".de", ".lu", ".fr")

_MAX_SOURCES = 3
_SCRAPE_TRUNCATE = 3000
_SEARCH_LIMIT = 5
_MAX_TOKENS = 1536


def _is_preferred(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if any(host.endswith(tld) for tld in _PREFERRED_TLDS):
        return True
    return any(key in host for key in _PREFERRED_HOSTS)


def _queries(make: str, model: str) -> list[str]:
    return [
        f"{make} {model} Varianten technische Daten kWh Reichweite",
        f"{make} {model} Probleme Rückruf KBA TÜV ADAC Mängel",
        f"{make} {model} bestes Baujahr gebraucht kaufen Erfahrungen",
    ]


async def _gather_sources(make: str, model: str, firecrawl) -> list[str]:
    """Search all queries, dedupe URLs, and rank DE/LU/FR sources first."""
    seen: list[str] = []
    seen_set: set[str] = set()
    for query in _queries(make, model):
        try:
            results = await firecrawl.search(query, limit=_SEARCH_LIMIT)
        except Exception as exc:  # noqa: BLE001 — research is best-effort
            logger.warning("guide search failed for %r: %s", query, exc)
            continue
        for item in results or []:
            url = (item or {}).get("url")
            if url and url not in seen_set:
                seen_set.add(url)
                seen.append(url)
    # Preferred (DE/LU/FR) sources first, original order otherwise.
    seen.sort(key=lambda u: 0 if _is_preferred(u) else 1)
    return seen[:_MAX_SOURCES]


async def _scrape_excerpts(urls: list[str], firecrawl) -> list[tuple[str, str]]:
    """Scrape each URL to truncated markdown; skip failures. -> [(url, excerpt)]."""
    out: list[tuple[str, str]] = []
    for url in urls:
        try:
            data = await firecrawl.scrape(url, formats=["markdown"])
        except Exception as exc:  # noqa: BLE001 — skip a bad source, keep going
            logger.warning("guide scrape failed for %s: %s", url, exc)
            continue
        markdown = (data or {}).get("markdown") or ""
        if markdown.strip():
            out.append((url, markdown[:_SCRAPE_TRUNCATE]))
    return out


def _build_user_text(
    make: str, model: str, excerpts: list[tuple[str, str]], existing_md: str | None
) -> str:
    parts = [
        f"Erstelle eine deutsche Kaufberatung für: {make} {model}.",
        "Nutze ausschließlich die folgenden Quellen-Auszüge (mit URLs):",
    ]
    for url, excerpt in excerpts:
        parts.append(f"\n--- QUELLE: {url} ---\n{excerpt}")
    if not excerpts:
        parts.append(
            "\n(Keine Quellen verfügbar — gib nur an, was gesichert allgemein "
            "bekannt und marktüblich ist; erfinde keine konkreten Zahlen.)"
        )
    if existing_md:
        parts.append(
            "\n--- BESTEHENDE GUIDE (ergänzen, nicht widersprechen) ---\n"
            + existing_md[:_SCRAPE_TRUNCATE]
        )
    return "\n".join(parts)


def _bump_revisions(existing_md: str | None) -> int:
    if not existing_md:
        return 1
    fm, _ = parse_front_matter(existing_md)
    try:
        return int(fm.get("revisions", "1")) + 1
    except (TypeError, ValueError):
        return 2


def _front_matter(make: str, model: str, data: dict, existing_md: str | None) -> str:
    fm_existing, _ = parse_front_matter(existing_md or "")
    year_range = data.get("year_range") or fm_existing.get("year_range") or "—"
    n_sources = len([s for s in (data.get("sources") or []) if s and s.get("url")])
    return (
        "---\n"
        f"make: {make}\n"
        f"model: {model}\n"
        "market: Germany (DE, optional LU/FR)\n"
        f"year_range: {year_range}\n"
        f"updated: {date.today().isoformat()}\n"
        f"revisions: {_bump_revisions(existing_md)}\n"
        f"sources: {n_sources}\n"
        "---\n"
    )


def _bullet_section(title: str, items: list[str] | None) -> str:
    rows = [f"- {i}" for i in (items or []) if i and i.strip()]
    body = "\n".join(rows) if rows else "_Keine belastbaren Angaben aus den Quellen._"
    return f"## {title}\n{body}\n"


def _sources_section(data: dict) -> str:
    rows = []
    for i, src in enumerate(data.get("sources") or [], start=1):
        if not src:
            continue
        url = src.get("url")
        if not url:
            continue
        title = src.get("title") or url
        rows.append(f"{i}. [{title}]({url})")
    body = "\n".join(rows) if rows else "_Keine Quellen verfügbar._"
    return f"## Sources\n{body}\n"


def _new_body(make: str, model: str, data: dict) -> str:
    overview = data.get("overview") or "_Übersicht folgt — begrenzte Quellenlage._"
    best_year = data.get("best_year")
    tips = list(data.get("buying_tips") or [])
    if best_year:
        tips = [f"Bestes Baujahr: {best_year}", *tips]
    return "\n".join(
        [
            f"# {make} {model} — Kaufberatung (DE)\n",
            f"> {overview}\n",
            _bullet_section("Variants & specs", data.get("variants")),
            f"## Battery cell suppliers\n"
            f"{data.get('battery_suppliers') or '_Keine belastbaren Angaben aus den Quellen._'}\n",
            _bullet_section("Known problems & recalls",
                            list(data.get("problems") or []) + list(data.get("recalls") or [])),
            _bullet_section("Buying tips — best year", tips),
            _sources_section(data),
        ]
    )


def render_markdown(
    make: str, model: str, data: dict, existing_md: str | None = None
) -> str:
    """Render the TEMPLATE markdown from extracted data.

    Fresh: front-matter + full body + a dated revision log.
    Enhance: keep the prior body verbatim, append the freshly-derived findings
    under a dated heading, and append a revision-log line. Never truncates."""
    today = date.today().isoformat()
    front_matter = _front_matter(make, model, data, existing_md)

    if not existing_md:
        body = _new_body(make, model, data)
        revision_log = f"## Revision log\n- {today} — initial guide.\n"
        return f"{front_matter}{body}\n{revision_log}"

    _, prior_body = parse_front_matter(existing_md)
    addition = _new_body(make, model, data)
    # Reduce the heading depth of the appended block so it nests under the prior body.
    addition_nested = "\n".join(
        ("#" + line if line.startswith("#") else line)
        for line in addition.splitlines()
    )
    appended = (
        f"\n## Update {today}\n\n{addition_nested}\n"
        f"\n- {today} — enhanced from new sources (revision "
        f"{_bump_revisions(existing_md)}).\n"
    )
    return f"{front_matter}{prior_body.rstrip()}\n{appended}"


async def generate_guide(
    make: str,
    model: str,
    *,
    provider,
    firecrawl,
    existing_md: str | None = None,
) -> str:
    """Research and synthesize a DE buyer's guide markdown for `make model`.

    Resilient: with no usable sources or AI disabled, still returns a minimal
    guide (front-matter + body noting limited sources) instead of raising."""
    urls = await _gather_sources(make, model, firecrawl)
    excerpts = await _scrape_excerpts(urls, firecrawl)
    user_text = _build_user_text(make, model, excerpts, existing_md)

    data: dict = {}
    try:
        result = await provider.extract_structured(
            model=SONNET,
            cached_system=GUIDE_SYSTEM,
            user_text=user_text,
            tool_name="model_guide",
            tool_schema=GUIDE_SCHEMA,
            tool_description="Structured German used-car buyer's guide fields.",
            max_tokens=_MAX_TOKENS,
        )
        data = result.data or {}
    except AIDisabledError:
        logger.warning("guide generation: AI disabled, emitting minimal guide")
    except Exception as exc:  # noqa: BLE001 — degrade to a minimal guide
        logger.warning("guide generation AI call failed: %s", exc)

    # If the AI omitted sources but we scraped some, surface the URLs we used.
    if not data.get("sources") and excerpts:
        data = {**data, "sources": [{"title": u, "url": u} for u, _ in excerpts]}

    return render_markdown(make, model, data, existing_md)


class GuideGenerator:
    """Thin wrapper binding a provider + firecrawl client to generate_guide."""

    def __init__(self, *, provider, firecrawl) -> None:
        self._provider = provider
        self._firecrawl = firecrawl

    async def generate_guide(
        self, make: str, model: str, *, existing_md: str | None = None
    ) -> str:
        return await generate_guide(
            make,
            model,
            provider=self._provider,
            firecrawl=self._firecrawl,
            existing_md=existing_md,
        )
