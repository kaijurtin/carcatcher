"""Model guides: serve researched per-model markdown guides (read-only).

Guides are plain `.md` files under `settings.guides_dir`, laid out as
`<make-slug>/<model-slug>.md` with a simple `---` front-matter block. Generation is
out-of-band (the `deep-research` skill, see model_guides/README.md); this router only
reads and serves them — it never mutates a guide.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from carcatcher.config import get_settings

logger = logging.getLogger(__name__)

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
    status: str = "ready"


class GenerateRequest(BaseModel):
    make: str
    model: str


class GuideDetail(BaseModel):
    make: str | None = None
    model: str | None = None
    front_matter: dict[str, str]
    markdown: str


def _guide_jobs() -> dict[str, dict]:
    """The in-flight guide-job map, or {} if AppState isn't initialized (tests)."""
    from carcatcher.app_state import get_state

    try:
        return get_state().guide_jobs
    except RuntimeError:
        return {}


@router.get("/models", response_model=list[GuideSummary])
def list_model_guides() -> list[GuideSummary]:
    """All ready guides (front-matter summary) plus any in-flight/failed jobs,
    sorted by make+model. Jobs whose guide file already exists are not duplicated."""
    root = get_settings().guides_dir
    out: list[GuideSummary] = []
    ready_slugs: set[str] = set()
    if root.exists():
        for path in sorted(root.rglob("*.md")):
            if path.name.lower() in _RESERVED:
                continue
            fm, body = parse_front_matter(path.read_text(encoding="utf-8"))
            make, model = fm.get("make"), fm.get("model")
            if make and model:
                ready_slugs.add(f"{slugify(make)}/{slugify(model)}")
            out.append(
                GuideSummary(
                    make=make, model=model,
                    title=_title(fm, body), updated=fm.get("updated"),
                    status="ready",
                )
            )
    # Surface generating/failed jobs the UI hasn't seen as ready files yet.
    for slug, job in _guide_jobs().items():
        if slug in ready_slugs or job.get("status") == "ready":
            continue
        make, model = job.get("make"), job.get("model")
        out.append(
            GuideSummary(
                make=make, model=model,
                title=f"{make} {model}".strip() or slug,
                updated=None, status=job.get("status", "generating"),
            )
        )
    out.sort(key=lambda g: ((g.make or "").lower(), (g.model or "").lower()))
    return out


async def _run_generation(make: str, model: str, slug: str) -> None:
    """Background task: generate (or enhance) a guide and persist it to guides_dir."""
    from carcatcher.app_state import get_state

    state = get_state()
    settings = get_settings()
    root = settings.guides_dir
    path = root / slugify(make) / f"{slugify(model)}.md"

    existing_md: str | None = None
    if path.is_file():
        existing_md = path.read_text(encoding="utf-8")

    try:
        markdown = await state.generator.generate_guide(
            make, model, existing_md=existing_md
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        state.guide_jobs[slug] = {"status": "ready", "make": make, "model": model}
    except Exception as exc:  # noqa: BLE001 — surfaced via the job log
        logger.exception("guide generation failed for %s", slug)
        state.guide_jobs[slug] = {
            "status": "failed", "make": make, "model": model, "error": str(exc)[:500],
        }


@router.post("/models/generate", status_code=202)
async def generate_model_guide(req: GenerateRequest) -> Response:
    """Kick off (or enhance) a guide generation in the background; returns 202.

    Idempotent while running: a second call for an already-generating slug returns
    202 without launching a duplicate task."""
    from carcatcher.app_state import get_state

    make, model = req.make.strip(), req.model.strip()
    if not make or not model:
        raise HTTPException(status_code=422, detail="make and model are required")
    slug = f"{slugify(make)}/{slugify(model)}"

    jobs = get_state().guide_jobs
    if jobs.get(slug, {}).get("status") == "generating":
        return Response(content='{"status":"generating"}', status_code=202,
                        media_type="application/json")

    jobs[slug] = {"status": "generating", "make": make, "model": model}
    asyncio.create_task(_run_generation(make, model, slug))
    return Response(content='{"status":"generating"}', status_code=202,
                    media_type="application/json")


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
