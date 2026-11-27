"""RSK-03: feed staleness is lazy and idle-quiet; never-ticked required feeds fail closed.

Fault-injection first: a silent source goes stale on read, a never-ticked
source fails closed in live mode, an optional feed going stale degrades
only its own stream, and the idle case stays healthy after 24 virtual
hours with no events. No network; all time comes from a FixtureClock.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pumpgrok.events.sources import SourceStatus
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.risk.breakers import DATA_STALE_S, DataStaleBreaker
from pumpgrok.risk.feed_health import (
    PRICE_FEED,
    FeedHealth,
    FeedSpec,
    feed_verdict,
)

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


# --- feed_verdict() function tests (pure function interface) ---


def test_fresh_feed_is_not_stale() -> None:
    verdict = feed_verdict(
        last_tick={PRICE_FEED: 100.0},
        subscribed={PRICE_FEED},
        required=frozenset(),
        now=150.0,
        stale_s=DATA_STALE_S,
        live=True,
    )
    assert verdict.stale == frozenset()
    assert verdict.tripped is False


def test_feed_silent_for_120s_is_stale() -> None:
    verdict = feed_verdict(
        last_tick={PRICE_FEED: 0.0},
        subscribed={PRICE_FEED},
        required=frozenset(),
        now=DATA_STALE_S,
        stale_s=DATA_STALE_S,
        live=False,
    )
    assert verdict.stale == frozenset({PRICE_FEED})
    assert verdict.tripped is True


def test_idle_desk_with_no_subscribed_mint_is_not_stale() -> None:
    verdict = feed_verdict(
        last_tick={PRICE_FEED: 0.0},
        subscribed=frozenset(),
        required=frozenset(),
        now=10_000.0,
        stale_s=DATA_STALE_S,
        live=True,
    )
    assert verdict.stale == frozenset()
    assert verdict.tripped is False


def test_never_ticked_required_feed_fails_closed_in_live_only() -> None:
    live = feed_verdict(
        last_tick={},
        subscribed=frozenset(),
        required={PRICE_FEED},
        now=0.0,
        stale_s=DATA_STALE_S,
        live=True,
    )
    paper = feed_verdict(
        last_tick={},
        subscribed=frozenset(),
        required={PRICE_FEED},
        now=0.0,
        stale_s=DATA_STALE_S,
        live=False,
    )
    assert live.never_ticked == frozenset({PRICE_FEED})
    assert live.tripped is True
    assert paper.never_ticked == frozenset()
    assert paper.tripped is False


def test_never_ticked_subscribed_feed_is_not_stale() -> None:
    verdict = feed_verdict(
        last_tick={},
        subscribed={PRICE_FEED},
        required=frozenset(),
        now=10_000.0,
        stale_s=DATA_STALE_S,
        live=True,
    )
    assert verdict.tripped is False


def test_data_stale_breaker_never_ticked_required_feed_fails_closed_in_live() -> None:
    now = [0.0]
    breaker = DataStaleBreaker(lambda: now[0], live=True, required_feeds=frozenset({PRICE_FEED}))
    assert breaker.evaluate(0.0) == "open"


def test_data_stale_breaker_never_ticked_required_feed_passes_in_paper() -> None:
    now = [0.0]
    breaker = DataStaleBreaker(lambda: now[0], live=False, required_feeds=frozenset({PRICE_FEED}))
    assert breaker.evaluate(0.0) == "closed"


def test_data_stale_breaker_idle_desk_is_quiet_after_a_tick() -> None:
    breaker = DataStaleBreaker(lambda: 0.0)
    breaker.note_tick(0.0)
    assert breaker.evaluate(10_000.0, subscribed=()) == "closed"


def test_data_stale_breaker_half_open_never_ticked_feed_trips_again() -> None:
    now = [0.0]
    breaker = DataStaleBreaker(lambda: now[0], live=True, required_feeds=frozenset({PRICE_FEED}))
    assert breaker.evaluate(0.0) == "open"
    now[0] = breaker.cooldown_s
    assert breaker.state == "half-open"
    assert breaker.evaluate(now[0]) == "open"
    assert breaker.trips == 2


def test_evaluate_reads_the_clock_only_when_asked() -> None:
    reads: list[float] = []

    def counting_now() -> float:
        reads.append(1.0)
        return 0.0

    breaker = DataStaleBreaker(counting_now, live=True, required_feeds=frozenset({PRICE_FEED}))
    breaker.note_tick(0.0)
    assert reads == []
    breaker.evaluate(10.0)
    assert reads == []
