"""Snapshot maintenance tests: mark-gone, prune, stale-run reclaim."""

from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session, select

from carcatcher.db.engine import get_engine
from carcatcher.db.models import (
    CrawlRun,
    Listing,
    ListingStatus,
    RunStatus,
    Shortlist,
    ShortlistItem,
    utcnow,
)
from carcatcher.pipeline.snapshot import (
    is_crawl_running,
    mark_gone,
    prune_gone,
    reclaim_stale_runs,
)


def test_mark_gone_only_unseen(test_engine):
    started = utcnow()
    with Session(get_engine()) as s:
        seen = Listing(source="kleinanzeigen", source_id="1", url="u1",
                       last_seen_at=started + timedelta(seconds=1))
        unseen = Listing(source="kleinanzeigen", source_id="2", url="u2",
                         last_seen_at=started - timedelta(hours=1))
        other = Listing(source="autoscout24", source_id="3", url="u3",
                        last_seen_at=started - timedelta(hours=1))
        s.add_all([seen, unseen, other])
        s.commit()

        n = mark_gone(s, "kleinanzeigen", started)
        assert n == 1
        rows = {r.source_id: r.status for r in s.exec(select(Listing)).all()}
        assert rows["1"] == ListingStatus.ACTIVE.value
        assert rows["2"] == ListingStatus.GONE.value
        assert rows["3"] == ListingStatus.ACTIVE.value  # different source untouched


def test_prune_removes_unreferenced_gone_only(test_engine):
    old = utcnow() - timedelta(days=30)
    with Session(get_engine()) as s:
        gone_old = Listing(source="kleinanzeigen", source_id="1", url="u1",
                           status=ListingStatus.GONE.value, last_seen_at=old)
        gone_shortlisted = Listing(source="kleinanzeigen", source_id="2", url="u2",
                                   status=ListingStatus.GONE.value, last_seen_at=old)
        gone_recent = Listing(source="kleinanzeigen", source_id="3", url="u3",
                              status=ListingStatus.GONE.value, last_seen_at=utcnow())
        s.add_all([gone_old, gone_shortlisted, gone_recent])
        s.commit()
        sl = Shortlist(name="default")
        s.add(sl)
        s.commit()
        s.add(ShortlistItem(shortlist_id=sl.id, listing_id=gone_shortlisted.id))
        s.commit()

        removed = prune_gone(s, prune_gone_days=14)
        assert removed == 1  # only the old, unreferenced one
        remaining = {r.source_id for r in s.exec(select(Listing)).all()}
        assert remaining == {"2", "3"}


def test_reclaim_stale_runs(test_engine):
    with Session(get_engine()) as s:
        stale = CrawlRun(source="kleinanzeigen", status=RunStatus.RUNNING.value,
                         started_at=utcnow() - timedelta(hours=2))
        fresh = CrawlRun(source="kleinanzeigen", status=RunStatus.RUNNING.value,
                         started_at=utcnow())
        s.add_all([stale, fresh])
        s.commit()

        n = reclaim_stale_runs(s, timeout_minutes=30)
        assert n == 1
        assert is_crawl_running(s) is True  # the fresh one still runs
