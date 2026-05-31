"""APScheduler setup: a single cron job that runs the crawl pipeline."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from carcatcher.config import get_settings
from carcatcher.pipeline.run import run_all_sources

logger = logging.getLogger(__name__)


async def scheduled_crawl() -> None:
    try:
        await run_all_sources(trigger="scheduled")
    except Exception:  # noqa: BLE001 — per-source errors already handled inside
        logger.exception("scheduled crawl failed")


def build_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        scheduled_crawl,
        CronTrigger.from_crontab(settings.cron_schedule, timezone="UTC"),
        id="crawl_kleinanzeigen",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler
