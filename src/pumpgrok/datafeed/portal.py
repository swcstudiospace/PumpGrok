"""PumpPortal free-method feed (R45): new-token and migration frames only.

No trade-stream key, no wallet, no signing import. Reconnect (including
TIMEOUT) goes through the SourceSupervisor; an interval with no frames
becomes a gap event; duplicate signatures across a reconnect are deduped.
Timings through the injected Clock. Transport-agnostic: the caller feeds
frames in.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pumpgrok.datafeed.bridge import publish
from pumpgrok.datafeed.events import GapEvent, Migrated, TokenCreated
from pumpgrok.datafeed.readonly import guarded_call
from pumpgrok.events.models import Event
from pumpgrok.replay.clock import FixtureClock, WallClock, format_ts_utc

EventSink = Callable[[Event], None]
RecordSink = Callable[[Any], None]


class RateLimiter:
    """One shared bucket: at most capacity acquires per window_s. Shed, never burst."""

    def __init__(self, clock: FixtureClock | WallClock, capacity: int = 30, window_s: float = 10.0):
        if capacity < 1:
            raise ValueError("limiter capacity must be at least 1")
        self._clock = clock
        self._capacity = capacity
        self._window_s = window_s
        self._window_start: float | None = None
        self._count = 0
        self._shed = 0

    @property
    def shed(self) -> int:
        return self._shed

    def _roll(self) -> None:
        now = self._clock.now()
        if self._window_start is None or now - self._window_start >= self._window_s:
            self._window_start = now
            self._count = 0

    def try_acquire(self) -> bool:
        self._roll()
        if self._count >= self._capacity:
            self._shed += 1
            return False
        self._count += 1
        return True


class PortalFeed:
    """PumpPortal create/migration frames with supervisor reconnect semantics."""

    def __init__(
        self,
        clock: FixtureClock | WallClock,
        limiter: RateLimiter,
        supervisor: Any,
        on_record: RecordSink,
        on_event: EventSink,
    ) -> None:
        self._clock = clock
        self._limiter = limiter
        self._supervisor = supervisor
        self._on_record = on_record
        self._on_event = on_event
        self._seen_signatures: set[str] = set()
        self._last_frame_at: float | None = None
        self.unknown_frames = 0

    def _emit(self, record: Any) -> None:
        self._on_record(record)
        publish(record, self._on_event)

    def _note_frame(self) -> None:
        now = self._clock.now()
        self._last_frame_at = now
        self._supervisor.note_frame(now)

    def handle_frame(self, frame: dict[str, Any]) -> bool:
        """Handle one inbound frame; True when it produced an event.

        Malformed frames count as unknown and never produce trades.
        """
        method = str(frame.get("method", ""))
        signature = str(frame.get("signature", ""))
        if signature:
            if signature in self._seen_signatures:
                return False
            self._seen_signatures.add(signature)
        builder = {"subscribeNewToken": TokenCreated, "subscribeMigration": Migrated}.get(method)
        if builder is None:
            self.unknown_frames += 1
            return False
        if not self._limiter.try_acquire():
            return False
        guarded_call(method, lambda: None)
        mint = str(frame.get("mint", ""))
        if not mint:
            self.unknown_frames += 1
            return False
        self._note_frame()
        self._emit(builder(mint=mint, ts_utc=format_ts_utc(self._clock.now())))
        return True

    def handle_timeout(self) -> GapEvent:
        """TIMEOUT reconnect: supervisor backoff; the silent interval is a gap."""
        now = self._clock.now()
        start = self._last_frame_at if self._last_frame_at is not None else now
        self._supervisor.note_failure()
        gap = GapEvent(
            mint=None,
            ts_utc=format_ts_utc(now),
            reason="timeout",
            from_ts_utc=format_ts_utc(start),
            to_ts_utc=format_ts_utc(now),
        )
        self._emit(gap)
        return gap
