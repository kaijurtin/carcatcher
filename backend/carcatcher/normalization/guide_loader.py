"""Load model-guide knowledge for the guide-aware categorizer.

Reads the served markdown guide for a make/model and returns just what the variant
agent needs: the "Variants & specs" section prose plus the `year_range` front-matter
value. Self-contained (no API-layer imports) so the crawl pipeline does not depend on
route code; the guide file layout (`<make-slug>/<model-slug>.md` + `---` front matter)
mirrors `api/routes/models.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from carcatcher.config import get_settings


@dataclass(frozen=True)
class GuideKnowledge:
    """The slice of a model guide the categorization agent reasons over."""

    make: str
    model: str
    year_range: str | None
    variants_section: str  # markdown prose of the "Variants & specs" section


def slugify(value: str) -> str:
    """'Volkswagen' -> 'volkswagen', 'ID.4' -> 'id-4', 'ID. Buzz' -> 'id-buzz'."""
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Split a leading `---` block of flat `key: value` lines from the markdown body."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            fm: dict[str, str] = {}
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    fm[key.strip()] = val.strip()
            return fm, parts[2].lstrip("\n")
    return {}, text


def _section(body: str, keyword: str) -> str | None:
    """Return the lines under the first level-2 (`## `) heading whose text contains
    `keyword` (case-insensitive), up to the next `## ` heading. None if not found."""
    lines = body.splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        if line.startswith("## "):
            if capturing:
                break  # reached the next section
            if keyword.lower() in line[3:].lower():
                capturing = True
            continue
        if capturing:
            out.append(line)
    if not capturing:
        return None
    text = "\n".join(out).strip()
    return text or None


def load_guide_knowledge(make: str, model: str) -> GuideKnowledge | None:
    """Load the guide for (make, model) and extract variant/year knowledge.

    Returns None when no guide exists or it has no recognizable variants section, so
    the caller can fall back to deterministic-only categorization.
    """
    root = get_settings().guides_dir.resolve()
    path = (root / slugify(make) / f"{slugify(model)}.md").resolve()
    # Path-traversal guard: resolved file must stay under the guides root.
    if root not in path.parents or not path.is_file():
        return None

    fm, body = _parse_front_matter(path.read_text(encoding="utf-8"))
    variants = _section(body, "variant")  # "## Variants & specs"
    if variants is None:
        return None
    return GuideKnowledge(
        make=fm.get("make") or make,
        model=fm.get("model") or model,
        year_range=fm.get("year_range"),
        variants_section=variants,
    )
