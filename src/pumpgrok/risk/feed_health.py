"""Lazy, idle-quiet feed health over ``SourceStatus`` (RSK-03, T-17-03).

Staleness is evaluated on read at check time from the injected Clock: no
timer, no thread, and no cached boolean. An idle desk (zero ticks and zero
held mints) reports healthy, never stale. Each feed declares required
versus optional; an optional feed going stale degrades only its own
stream. In paper mode a never-ticked required feed degrades; in live mode
it fails closed and blocks entries.

Time comes only from the Clock; this module never reads the wall clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from pumpgrok.events.sources import SourceStatus

if TYPE_CHECKING:
    from pumpgrok.core.ids import Clock

__all__ = ["STALE_AFTER_S", "FeedHealth", "FeedSpec", "FeedVerdict"]

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

    def check(self, mode: Mode = "paper", *, held_mints: int = 0) -> FeedVerdict:
        """Evaluate every feed on read and return one verdict.

        Idle-quiet: with zero ticks ever recorded and zero held mints the
        desk is healthy even if required feeds have never ticked.
        """
        if not self._last_tick and held_mints <= 0:
            return FeedVerdict(status="healthy", detail="idle desk: no ticks, no held mints")
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
                return FeedVerdict(
                    status="failed",
                    stale_feeds=tuple(stale),
                    never_ticked=tuple(never_ticked),
                    detail=f"required feeds unhealthy in live mode: {bad}",
                )
            return FeedVerdict(
                status="degraded",
                stale_feeds=tuple(stale),
                never_ticked=tuple(never_ticked),
                detail=f"required feeds unhealthy: {tuple(required_failed)}",
            )
        if optional_stale:
            return FeedVerdict(
                status="degraded",
                stale_feeds=tuple(stale),
                never_ticked=tuple(never_ticked),
                detail=f"optional feeds stale: {tuple(optional_stale)}",
            )
        return FeedVerdict(
            status="healthy", stale_feeds=tuple(stale), never_ticked=tuple(never_ticked)
        )
