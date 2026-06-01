"""Model guides: serve researched per-model markdown guides (read-only).

Guides are plain `.md` files under `settings.guides_dir`, laid out as
`<make-slug>/<model-slug>.md` with a simple `---` front-matter block. Generation is
out-of-band (the `deep-research` skill, see model_guides/README.md); this router only
reads and serves them — it never mutates a guide.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from carcatcher.config import get_settings

router = APIRouter()

_RESERVED = {"template.md", "readme.md"}


def slugify(value: str) -> str:
    """'Volkswagen' -> 'volkswagen', 'ID.4' -> 'id-4', 'ID. Buzz' -> 'id-buzz'."""
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Split a leading `---` block of flat `key: value` lines from the markdown body."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            fm = {}
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    fm[key.strip()] = val.strip()
            return fm, parts[2].lstrip("\n")
    return {}, text


def _title(fm: dict[str, str], body: str) -> str:
    if fm.get("make") and fm.get("model"):
        return f"{fm['make']} {fm['model']}"
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "Untitled guide"


class GuideSummary(BaseModel):
    make: str | None = None
    model: str | None = None
    title: str
    updated: str | None = None


class GuideDetail(BaseModel):
    make: str | None = None
    model: str | None = None
    front_matter: dict[str, str]
    markdown: str


@router.get("/models", response_model=list[GuideSummary])
def list_model_guides() -> list[GuideSummary]:
    """All available guides (front-matter summary), sorted by make+model."""
    root = get_settings().guides_dir
    if not root.exists():
        return []
    out: list[GuideSummary] = []
    for path in sorted(root.rglob("*.md")):
        if path.name.lower() in _RESERVED:
            continue
        fm, body = parse_front_matter(path.read_text(encoding="utf-8"))
        out.append(
            GuideSummary(
                make=fm.get("make"), model=fm.get("model"),
                title=_title(fm, body), updated=fm.get("updated"),
            )
        )
    out.sort(key=lambda g: ((g.make or "").lower(), (g.model or "").lower()))
    return out


@router.get("/models/{make}/{model}/research", response_model=GuideDetail)
def get_model_guide(make: str, model: str) -> GuideDetail:
    """Return one guide's front-matter + markdown body, or 404."""
    root = get_settings().guides_dir.resolve()
    path = (root / slugify(make) / f"{slugify(model)}.md").resolve()
    # Path-traversal guard: resolved file must stay under the guides root.
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="model guide not found")
    fm, body = parse_front_matter(path.read_text(encoding="utf-8"))
    return GuideDetail(
        make=fm.get("make") or make, model=fm.get("model") or model,
        front_matter=fm, markdown=body,
    )
