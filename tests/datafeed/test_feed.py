"""Feed: TIMEOUT reconnect dedup, gap events, 30/10s limiter (MKT-06)."""

from __future__ import annotations

import random
from pathlib import Path

from .fake_feed import FakeFeed
from pumpgrok.datafeed.events import GapEvent
from pumpgrok.datafeed.portal import PortalFeed, RateLimiter
from pumpgrok.events.sources import SourceStatus, SourceSupervisor
from pumpgrok.replay.clock import FixtureClock


def _harness(tmp_path: Path) -> tuple[PortalFeed, FakeFeed, FixtureClock, RateLimiter]:
    clock = FixtureClock(1_000.0)
    supervisor = SourceSupervisor(clock, random.Random(1), path=tmp_path / "events.sqlite")
    limiter = RateLimiter(clock, capacity=30, window_s=10.0)
    fake = FakeFeed()
    feed = PortalFeed(clock, limiter, supervisor, fake.on_record, fake.on_event)
    return feed, fake, clock, limiter


def test_timeout_reconnect_no_duplicate_signature(tmp_path: Path) -> None:
    feed, fake, clock, _ = _harness(tmp_path)
    assert feed.handle_frame({"method": "subscribeNewToken", "mint": "m1", "signature": "s1"})
    clock.advance_to(1_030.0)
    gap = feed.handle_timeout()
    assert isinstance(gap, GapEvent)
    assert gap.reason == "timeout"
    # Reconnected frame with the same signature is deduped.
    assert feed.handle_frame({"method": "subscribeNewToken", "mint": "m1", "signature": "s1"}) is False
    assert len([r for r in fake.records if getattr(r, "mint", None) == "m1"]) == 1
    assert gap in fake.records


def test_gap_event_on_bus(tmp_path: Path) -> None:
    feed, fake, clock, _ = _harness(tmp_path)
    clock.advance_to(1_030.0)
    feed.handle_timeout()
    assert fake.events and fake.events[-1].kind.value == "gap"


def test_limiter_flood_sheds_with_backpressure(tmp_path: Path) -> None:
    feed, fake, clock, limiter = _harness(tmp_path)
    accepted = 0
    for i in range(60):
        if feed.handle_frame({"method": "subscribeNewToken", "mint": f"m{i}", "signature": f"s{i}"}):
            accepted += 1
    assert accepted == 30  # never bursts beyond the window
    assert limiter.shed == 30
    clock.advance_to(1_011.0)
    assert feed.handle_frame({"method": "subscribeNewToken", "mint": "late", "signature": "late"})


def test_malformed_frame_counts_unknown(tmp_path: Path) -> None:
    feed, fake, _, _ = _harness(tmp_path)
    assert feed.handle_frame({"method": "subscribeNewToken"}) is False
    assert feed.unknown_frames == 1
    assert fake.records == []


def test_supervisor_backoff_after_timeout(tmp_path: Path) -> None:
    feed, fake, clock, _ = _harness(tmp_path)
    clock.advance_to(1_030.0)
    feed.handle_timeout()
    assert feed._supervisor.status_at(clock.now()) is SourceStatus.disconnected
