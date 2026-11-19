"""RSK-03: staleness is lazy and idle-quiet; a never-ticked required feed fails closed live."""

from __future__ import annotations

from pumpgrok.risk.breakers import DATA_STALE_S, DataStaleBreaker
from pumpgrok.risk.feed_health import PRICE_FEED, feed_verdict


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
