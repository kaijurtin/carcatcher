"""Seed the configured guides directory from the repo-bundled tree.

When MODEL_GUIDES_DIR points at a persistent volume (e.g. /data), the bundled
guides shipped in the repo are copied there once, so the first deploy serves the
curated guides and subsequent generations write alongside them.
"""

from __future__ import annotations

import logging
import shutil

from carcatcher.config import get_settings

logger = logging.getLogger(__name__)


def seed_guides_dir() -> None:
    """Copy bundled guides into the configured guides_dir when it is empty.

    No-op when guides_dir IS the bundled dir, or when it already holds any .md
    file (so user/generated guides are never overwritten)."""
    settings = get_settings()
    target = settings.guides_dir.resolve()
    bundled = settings.bundled_guides_dir.resolve()
    if target == bundled:
        return
    if not bundled.exists():
        return
    if any(target.rglob("*.md")) if target.exists() else False:
        return

    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundled, target, dirs_exist_ok=True)
    logger.info("seeded model guides from %s into %s", bundled, target)
