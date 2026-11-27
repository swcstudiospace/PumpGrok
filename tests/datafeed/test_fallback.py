"""Feed fallback: degraded behavior is honest; never invented ticks."""

from __future__ import annotations

from pumpgrok.datafeed.fallback import FeedFallback


def test_no_transport_is_stale_with_no_ticks() -> None:
    feed = FeedFallback()
    assert feed.has_transport is False
    assert feed.read() == (True, [])


def test_transport_present_is_not_stale() -> None:
    feed = FeedFallback(transport=object())
    assert feed.has_transport is True
    stale, ticks = feed.read()
    assert stale is False
    assert ticks == []
