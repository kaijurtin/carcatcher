"""Snapshot maintenance tests: per-search mark-gone, status recompute, prune."""

from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session, select

from carcatcher.db.engine import get_engine
from carcatcher.db.models import (
    CrawlRun,
    Listing,
    ListingSearch,
    ListingStatus,
    RunStatus,
    SavedSearch,
    Shortlist,
    ShortlistItem,
    utcnow,
)
from carcatcher.pipeline.snapshot import (
    is_crawl_running,
    mark_gone_for_search,
    prune,
    reclaim_stale_runs,
    recompute_listing_status,
)


def _seed_listing(s: Session, sid: str, **over) -> Listing:
    li = Listing(source="kleinanzeigen", source_id=sid, url=f"u{sid}", **over)
    s.add(li)
    s.commit()
    s.refresh(li)
    return li


def _link(s: Session, search_id: int, listing_id: int, *, last_seen, status="active") -> None:
    s.add(ListingSearch(search_id=search_id, listing_id=listing_id,
                        status=status, last_seen_at=last_seen))
    s.commit()


def test_mark_gone_is_per_search(test_engine):
    started = utcnow()
    with Session(get_engine()) as s:
        s.add_all([SavedSearch(name="A"), SavedSearch(name="B")])
        s.commit()
        a, b = s.exec(select(SavedSearch)).all()
        li1, li2, li3 = _seed_listing(s, "1"), _seed_listing(s, "2"), _seed_listing(s, "3")
        _link(s, a.id, li1.id, last_seen=started + timedelta(seconds=1))   # seen this run
        _link(s, a.id, li2.id, last_seen=started - timedelta(hours=1))     # stale in A
        _link(s, b.id, li3.id, last_seen=started - timedelta(hours=1))     # stale but in B

        n = mark_gone_for_search(s, a.id, started)
        assert n == 1
        statuses = {(x.search_id, x.listing_id): x.status for x in s.exec(select(ListingSearch)).all()}
        assert statuses[(a.id, li1.id)] == "active"
        assert statuses[(a.id, li2.id)] == "gone"
        assert statuses[(b.id, li3.id)] == "active"  # search B untouched


def test_recompute_listing_status(test_engine):
    with Session(get_engine()) as s:
        s.add(SavedSearch(name="A"))
        s.commit()
        a = s.exec(select(SavedSearch)).one()
        active_li = _seed_listing(s, "1", status="gone")
        gone_li = _seed_listing(s, "2", status="active")
        _link(s, a.id, active_li.id, last_seen=utcnow(), status="active")
        _link(s, a.id, gone_li.id, last_seen=utcnow(), status="gone")

        recompute_listing_status(s)
        rows = {x.source_id: x.status for x in s.exec(select(Listing)).all()}
        assert rows["1"] == "active"  # has an active link
        assert rows["2"] == "gone"    # only gone links


def test_prune_deletes_orphans_and_old_gone_links(test_engine):
    old = utcnow() - timedelta(days=30)
    with Session(get_engine()) as s:
        s.add(SavedSearch(name="A"))
        s.commit()
        a = s.exec(select(SavedSearch)).one()
        linked = _seed_listing(s, "1")           # has an active link → keep
        orphan = _seed_listing(s, "2")           # no links → delete
        shortlisted_orphan = _seed_listing(s, "3")  # no links but shortlisted → keep
        _link(s, a.id, linked.id, last_seen=utcnow(), status="active")
        # an old gone link → its row pruned (but listing 1 stays via active link)
        _link(s, a.id, _seed_listing(s, "4").id, last_seen=old, status="gone")

        sl = Shortlist(name="default")
        s.add(sl)
        s.commit()
        s.add(ShortlistItem(shortlist_id=sl.id, listing_id=shortlisted_orphan.id))
        s.commit()

        removed = prune(s, prune_gone_days=14)
        remaining = {x.source_id for x in s.exec(select(Listing)).all()}
        # orphan "2" and "4" (gone-link orphan) deleted; "1" + shortlisted "3" survive
        assert "2" not in remaining
        assert "1" in remaining and "3" in remaining
        assert removed >= 1


def test_reclaim_and_is_running(test_engine):
    with Session(get_engine()) as s:
        s.add_all([
            CrawlRun(source="A", status=RunStatus.RUNNING.value,
                     started_at=utcnow() - timedelta(hours=2)),
            CrawlRun(source="B", status=RunStatus.RUNNING.value, started_at=utcnow()),
        ])
        s.commit()
        assert reclaim_stale_runs(s, timeout_minutes=30) == 1
        assert is_crawl_running(s) is True
