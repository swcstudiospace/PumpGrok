"""RSK-03: feed staleness is lazy and idle-quiet; never-ticked required feeds fail closed.

Fault-injection first: a silent source goes stale on read, a never-ticked
source fails closed in live mode, an optional feed going stale degrades
only its own stream, and the idle case stays healthy after 24 virtual
hours with no events. No network; all time comes from a FixtureClock.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.events.sources import SourceStatus
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.risk.feed_health import FeedHealth, FeedSpec

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()


def _health(clock: FixtureClock) -> FeedHealth:
    health = FeedHealth(clock)
    health.register(FeedSpec("curve", required=True, stale_after_s=120.0))
    health.register(FeedSpec("social", required=False, stale_after_s=120.0))
    return health


def test_idle_desk_is_quiet_after_24_virtual_hours() -> None:
    clock = FixtureClock(start=START)
    health = _health(clock)
    clock.jump(24 * 3600.0)
    verdict = health.check("live", held_mints=0)
    assert verdict.status == "healthy"
    assert verdict.blocks_entries() is False


def test_never_ticked_required_feed_degrades_in_paper() -> None:
    clock = FixtureClock(start=START)
    health = _health(clock)
    verdict = health.check("paper", held_mints=3)
    assert verdict.status == "degraded"
    assert verdict.blocks_entries() is False
    assert "curve" in verdict.never_ticked


def test_never_ticked_required_feed_fails_closed_in_live() -> None:
    clock = FixtureClock(start=START)
    health = _health(clock)
    verdict = health.check("live", held_mints=3)
    assert verdict.status == "failed"
    assert verdict.blocks_entries() is True
    assert "curve" in verdict.never_ticked


def test_staleness_is_lazy_and_computed_on_read() -> None:
    clock = FixtureClock(start=START)
    health = _health(clock)
    health.note_tick("curve")
    assert health.status_of("curve") is SourceStatus.live
    clock.jump(121.0)
    # No tick call happened: the status changed only because time moved.
    assert health.status_of("curve") is SourceStatus.stale
    verdict = health.check("live", held_mints=1)
    assert verdict.status == "failed"
    assert "curve" in verdict.stale_feeds


def test_optional_feed_stale_degrades_only_its_own_stream() -> None:
    clock = FixtureClock(start=START)
    health = _health(clock)
    health.note_tick("curve")
    clock.jump(121.0)
    health.note_tick("curve")
    verdict = health.check("live", held_mints=1)
    assert verdict.status == "degraded"
    assert verdict.blocks_entries() is False
    assert "social" in verdict.never_ticked
    assert "curve" not in verdict.never_ticked
    assert "curve" not in verdict.stale_feeds


def test_ticked_fresh_feed_is_healthy() -> None:
    clock = FixtureClock(start=START)
    health = _health(clock)
    health.note_tick("curve")
    health.note_tick("social")
    verdict = health.check("live", held_mints=2)
    assert verdict.status == "healthy"
    assert verdict.blocks_entries() is False
