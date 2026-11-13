"""Bounded recovery for feeds: rolling-window limiter, dedup window, gap ledger, reconnect.

A feed's frame source may raise a transport failure. Recovery marks the source
disconnected, opens a gap, backs off on the injected clock, reconnects, reseeds the held
subscriptions and closes the gap at the moment the reseed succeeds, even when no later
trade arrives. Every failed attempt is counted so backoff keeps growing.
"""

from __future__ import annotations

import asyncio
import math
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from pumpgrok.events.sources import SourceSupervisor
from pumpgrok.replay.clock import Clock

# Transport failures a feed recovers from. Anything else is a programming error and
# propagates. ReadOnlyBoundary wraps transport exceptions as RuntimeError.
TRANSPORT_FAILURES = (TimeoutError, OSError, RuntimeError)


class FrameSource(Protocol):
    async def next_frame(self) -> object:
        """Return the next decoded frame; raise TimeoutError on silence."""
        ...

    async def reconnect(self) -> None:
        """Reopen the stream. Subscriptions are reseeded by the feed afterwards."""
        ...


class RollingWindowLimiter:
    """At most ``limit`` operations in any half-open window of ``window_s`` seconds.

    An operation at time t is admitted only when fewer than ``limit`` admitted
    operations lie in (t - window_s, t]. Waits run on the injected clock.
    """

    def __init__(self, clock: Clock, *, limit: int = 30, window_s: float = 10.0) -> None:
        if type(limit) is not int or limit <= 0:
            raise ValueError("limit must be a positive integer")
        if isinstance(window_s, bool) or not math.isfinite(window_s) or window_s <= 0:
            raise ValueError("window_s must be a positive finite number")
        self._clock = clock
        self._limit = limit
        self._window_s = float(window_s)
        self._stamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """Wait until an operation is admitted. Returns the seconds waited."""
        waited = 0.0
        async with self._lock:
            while True:
                now = self._clock.monotonic()
                while self._stamps and now - self._stamps[0] >= self._window_s:
                    self._stamps.popleft()
                if len(self._stamps) < self._limit:
                    self._stamps.append(now)
                    return waited
                delay = self._window_s - (now - self._stamps[0])
                waited += delay
                await self._clock.sleep(delay)


class DedupWindow:
    """Bounded memory of recently admitted keys. Eviction is first-admitted-first-forgotten."""

    def __init__(self, *, capacity: int) -> None:
        if type(capacity) is not int or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        self._capacity = capacity
        self._keys: dict[tuple[str, int], None] = {}

    def __len__(self) -> int:
        return len(self._keys)

    def admit(self, key: tuple[str, int]) -> bool:
        """True the first time a key is seen within the window; False for a duplicate."""
        if key in self._keys:
            return False
        self._keys[key] = None
        while len(self._keys) > self._capacity:
            del self._keys[next(iter(self._keys))]
        return True


@dataclass(frozen=True, slots=True)
class Gap:
    start_ts_utc: str
    end_ts_utc: str | None
    reason: str


class GapLedger:
    """Explicit unrecoverable intervals.

    Each closed gap reaches ``sink`` before it is kept, up to ``capacity`` in memory.
    """

    def __init__(
        self,
        clock: Clock,
        *,
        capacity: int = 256,
        sink: Callable[[Gap], None] | None = None,
    ) -> None:
        if type(capacity) is not int or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        self._clock = clock
        self._closed: deque[Gap] = deque(maxlen=capacity)
        self._pending: tuple[str, str] | None = None
        self._sink = sink

    @property
    def gaps(self) -> tuple[Gap, ...]:
        return tuple(self._closed)

    @property
    def open_gap(self) -> bool:
        return self._pending is not None

    def open(self, reason: str) -> None:
        """Start a gap at the injected clock. An already-open gap keeps its start."""
        if self._pending is None:
            self._pending = (self._clock.utc_iso(), reason)

    def close(self) -> None:
        """End the open gap at the injected clock, if any."""
        if self._pending is None:
            return
        start, reason = self._pending
        self._finish(Gap(start_ts_utc=start, end_ts_utc=self._clock.utc_iso(), reason=reason))
        self._pending = None

    def record_loss(self, reason: str) -> None:
        """Record a single unrecoverable point that has no duration."""
        now = self._clock.utc_iso()
        self._finish(Gap(start_ts_utc=now, end_ts_utc=now, reason=reason))

    def _finish(self, gap: Gap) -> None:
        """Hand a closed gap to the sink before keeping it, so a failed write records nothing."""
        if self._sink is not None:
            self._sink(gap)
        self._closed.append(gap)


@dataclass
class FeedStats:
    received: int = 0
    applied: int = 0
    duplicate: int = 0
    failed_tx: int = 0
    undecodable: int = 0
    unwatched: int = 0
    malformed: int = 0


class Recovery:
    """Turns frame-source failures into disconnected state, backoff, reconnect and resync."""

    def __init__(
        self,
        *,
        clock: Clock,
        supervisor: SourceSupervisor,
        frames: FrameSource,
        gaps: GapLedger,
        subscribe: Callable[[], Awaitable[None]],
        held: Callable[[], Sequence[str]],
    ) -> None:
        self._clock = clock
        self._supervisor = supervisor
        self._frames = frames
        self._gaps = gaps
        self._subscribe = subscribe
        self._held = held

    async def receive(self) -> object | None:
        """Return the next frame, or None when a failure was recovered this call."""
        try:
            frame = await self._frames.next_frame()
        except TRANSPORT_FAILURES as exc:
            await self._recover(type(exc).__name__)
            return None
        self._supervisor.note_frame(self._clock.now())
        return frame

    async def _recover(self, reason: str) -> None:
        self._supervisor.note_failure()
        self._gaps.open(reason)
        while True:
            await self._clock.sleep(self._supervisor.next_delay_s())
            try:
                await self._frames.reconnect()
                self._supervisor.resync(list(self._held()))
                await self._subscribe()
            except TRANSPORT_FAILURES:
                self._supervisor.note_failure()
                continue
            self._gaps.close()
            return
