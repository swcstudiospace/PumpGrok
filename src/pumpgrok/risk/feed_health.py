"""Feed health verdict: lazy staleness and the never-ticked fail-closed rule (RSK-03).

Pure: no clock reads and no timers. The caller passes ``now`` at check time, so
staleness is evaluated only when a breaker is asked for a verdict and an idle
desk with no subscribed feed is never stale.

Also provides ``FeedHealth`` (clock-driven) for callers that prefer an object
interface; both share the same staleness rule.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from pumpgrok.events.sources import SourceStatus

if TYPE_CHECKING:
    from pumpgrok.core.ids import Clock

#: The desk-wide price feed observed by ``DataStaleBreaker``.
PRICE_FEED = "price"

#: TODO(owner): the list of required feeds is an open owner decision (index Finding 7).
#: No decision or constant in the repo defines it; the owner supplies it here. Empty
#: means no feed is required, so a never-ticked feed never fails closed.
REQUIRED_FEEDS: frozenset[str] = frozenset()

#: Staleness window per feed, seconds (mirrors events STALE_AFTER_S).
STALE_AFTER_S = 120.0

Mode = Literal["paper", "live"]


@dataclass(frozen=True)
class FeedSpec:
    """One named feed; required feeds can fail the desk closed in live mode."""

    name: str
    required: bool = True
    stale_after_s: float = STALE_AFTER_S


@dataclass(frozen=True)
class FeedVerdict:
    """Feeds that are stale, and required feeds that never ticked in live mode."""

    stale: frozenset[str]
    never_ticked: frozenset[str]

    @property
    def tripped(self) -> bool:
        return bool(self.stale or self.never_ticked)


@dataclass(frozen=True)
class LegacyFeedVerdict:
    """One lazy staleness evaluation: healthy, degraded, or failed closed."""

    status: Literal["healthy", "degraded", "failed"]
    stale_feeds: tuple[str, ...] = ()
    never_ticked: tuple[str, ...] = ()
    detail: str = ""

    def blocks_entries(self) -> bool:
        """True only when the verdict fails closed (live, required feed)."""
        return self.status == "failed"


@dataclass
class FeedHealth:
    """On-read staleness over tick timestamps supplied by the caller."""

    clock: Clock
    feeds: dict[str, FeedSpec] = field(default_factory=dict)
    _last_tick: dict[str, float] = field(default_factory=dict)

    def register(self, spec: FeedSpec) -> None:
        """Declare one feed (required or optional)."""
        self.feeds[spec.name] = spec

    def note_tick(self, feed: str, ts: float | None = None) -> None:
        """Record a tick for one feed; defaults to the injected Clock."""
        self._last_tick[feed] = self.clock.now() if ts is None else ts

    def status_of(self, feed: str) -> SourceStatus:
        """SourceStatus for one feed, evaluated lazily from the Clock."""
        spec = self.feeds.get(feed)
        if spec is None:
            return SourceStatus.disconnected
        last = self._last_tick.get(feed)
        if last is None:
            return SourceStatus.disconnected
        if self.clock.now() - last > spec.stale_after_s:
            return SourceStatus.stale
        return SourceStatus.live

    def check(self, mode: Mode = "paper", *, held_mints: int = 0) -> LegacyFeedVerdict:
        """Evaluate every feed on read and return one verdict.

        Idle-quiet: with zero ticks ever recorded and zero held mints the
        desk is healthy even if required feeds have never ticked.
        """
        if not self._last_tick and held_mints <= 0:
            return LegacyFeedVerdict(status="healthy", detail="idle desk: no ticks, no held mints")
        stale: list[str] = []
        never_ticked: list[str] = []
        required_failed: list[str] = []
        optional_stale: list[str] = []
        for name, spec in self.feeds.items():
            status = self.status_of(name)
            if status is SourceStatus.live:
                continue
            if name not in self._last_tick:
                never_ticked.append(name)
            else:
                stale.append(name)
            if spec.required:
                required_failed.append(name)
            else:
                optional_stale.append(name)
        if required_failed:
            if mode == "live":
                bad = tuple(required_failed)
                return LegacyFeedVerdict(
                    status="failed",
                    stale_feeds=tuple(stale),
                    never_ticked=tuple(never_ticked),
                    detail=f"required feeds unhealthy in live mode: {bad}",
                )
            return LegacyFeedVerdict(
                status="degraded",
                stale_feeds=tuple(stale),
                never_ticked=tuple(never_ticked),
                detail=f"required feeds unhealthy: {tuple(required_failed)}",
            )
        if optional_stale:
            return LegacyFeedVerdict(
                status="degraded",
                stale_feeds=tuple(stale),
                never_ticked=tuple(never_ticked),
                detail=f"optional feeds stale: {tuple(optional_stale)}",
            )
        return LegacyFeedVerdict(
            status="healthy", stale_feeds=tuple(stale), never_ticked=tuple(never_ticked)
        )


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
