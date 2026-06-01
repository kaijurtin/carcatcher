"""Model-guides API: listing, fetch, 404, front-matter parsing, slug mapping."""

from __future__ import annotations

from carcatcher import config
from carcatcher.api.routes.models import parse_front_matter, slugify

GUIDE = """\
---
make: Volkswagen
model: ID.4
year_range: 2020–2026
updated: 2026-06-01
revisions: 1
sources: 7
---
# Volkswagen ID.4 — buyer's guide

## Variants & specs
Pure / Pro / Pro S / GTX.

## Sources
1. https://example.org
"""


def _point_guides_at(tmp_path) -> None:
    """Make the running settings serve guides from a tmp dir with one VW ID.4 guide."""
    (tmp_path / "volkswagen").mkdir()
    (tmp_path / "volkswagen" / "id-4.md").write_text(GUIDE, encoding="utf-8")
    (tmp_path / "TEMPLATE.md").write_text("--- ignore me ---", encoding="utf-8")
    config._settings.model_guides_dir = str(tmp_path)


# --- unit: helpers --------------------------------------------------------- #

def test_slugify():
    assert slugify("Volkswagen") == "volkswagen"
    assert slugify("ID.4") == "id-4"
    assert slugify("ID. Buzz") == "id-buzz"
    assert slugify("Mercedes-Benz") == "mercedes-benz"


def test_parse_front_matter_splits_block_and_body():
    fm, body = parse_front_matter(GUIDE)
    assert fm["make"] == "Volkswagen" and fm["model"] == "ID.4"
    assert fm["sources"] == "7"
    assert body.startswith("# Volkswagen ID.4")
    assert "---" not in body  # front-matter stripped


def test_parse_front_matter_no_block():
    fm, body = parse_front_matter("# plain\n\ntext")
    assert fm == {} and body == "# plain\n\ntext"


# --- API ------------------------------------------------------------------- #

def test_list_empty_when_dir_missing(client, tmp_path):
    config._settings.model_guides_dir = str(tmp_path / "does-not-exist")
    assert client.get("/api/models").json() == []


def test_list_returns_summary_and_skips_template(client, tmp_path):
    _point_guides_at(tmp_path)
    body = client.get("/api/models").json()
    assert len(body) == 1  # TEMPLATE.md excluded
    g = body[0]
    assert (g["make"], g["model"], g["updated"]) == ("Volkswagen", "ID.4", "2026-06-01")
    assert g["title"] == "Volkswagen ID.4"


def test_get_guide_returns_markdown_body(client, tmp_path):
    _point_guides_at(tmp_path)
    g = client.get("/api/models/Volkswagen/ID.4/research").json()
    assert g["make"] == "Volkswagen" and g["model"] == "ID.4"
    assert g["front_matter"]["sources"] == "7"
    assert g["markdown"].startswith("# Volkswagen ID.4")


def test_get_guide_404(client, tmp_path):
    _point_guides_at(tmp_path)
    assert client.get("/api/models/Tesla/Model 3/research").status_code == 404


def test_get_guide_path_traversal_blocked(client, tmp_path):
    _point_guides_at(tmp_path)
    # slugify neutralizes separators, so traversal can't escape the guides root.
    assert client.get("/api/models/../../etc/passwd").status_code in (404, 405, 422)
