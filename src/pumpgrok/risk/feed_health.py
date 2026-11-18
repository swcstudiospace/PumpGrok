"""Feed health verdict: lazy staleness and the never-ticked fail-closed rule (RSK-03).

Pure: no clock reads and no timers. The caller passes ``now`` at check time, so
staleness is evaluated only when a breaker is asked for a verdict and an idle
desk with no subscribed feed is never stale.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass

#: The desk-wide price feed observed by ``DataStaleBreaker``.
PRICE_FEED = "price"

#: TODO(owner): the list of required feeds is an open owner decision (index Finding 7).
#: No decision or constant in the repo defines it; the owner supplies it here. Empty
#: means no feed is required, so a never-ticked feed never fails closed.
REQUIRED_FEEDS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class FeedVerdict:
    """Feeds that are stale, and required feeds that never ticked in live mode."""

    stale: frozenset[str]
    never_ticked: frozenset[str]

    @property
    def tripped(self) -> bool:
        return bool(self.stale or self.never_ticked)


def feed_verdict(
    *,
    last_tick: Mapping[str, float | None],
    subscribed: Collection[str],
    required: Collection[str],
    now: float,
    stale_s: float,
    live: bool,
) -> FeedVerdict:
    """Judge feed health at ``now``.

    A subscribed feed is stale once its last tick is ``stale_s`` or more old. A
    subscribed feed that has never ticked is not stale: it has nothing to age.
    A required feed that never ticked fails closed, but only in live mode.
    """
    stale = frozenset(
        feed
        for feed in subscribed
        if (seen := last_tick.get(feed)) is not None and now - seen >= stale_s
    )
    never_ticked = frozenset(feed for feed in required if live and last_tick.get(feed) is None)
    return FeedVerdict(stale=stale, never_ticked=never_ticked)
