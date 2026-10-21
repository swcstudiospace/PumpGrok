"""Time sources (paper-engine.md 4.2, R27).

This is the only module in src/pumpgrok allowed to import `time`, `asyncio.sleep`,
`asyncio.timeout` or `asyncio.wait_for`. tests/safety/test_static_guards.py enforces
it. Everything else reads time through an injected Clock, so a replay reproduces
every timestamp, id and retry delay from the fixture alone.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import time
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """The only time source. Every id, audit row, timeout and retry wait reads it."""

    def now(self) -> float: ...  # epoch seconds (UTC)

    def monotonic(self) -> float: ...

    def utc_iso(self) -> str: ...

    async def sleep(self, seconds: float) -> None: ...

    def timeout(self, seconds: float) -> AbstractAsyncContextManager[None]: ...


def format_ts_utc(epoch: float) -> str:
    """Render epoch seconds as the ledger `ts_utc` form, e.g. 2026-01-01T00:00:00.000001Z."""
    text = datetime.fromtimestamp(epoch, UTC).isoformat(timespec="microseconds")
    return text.replace("+00:00", "Z")


def parse_ts_utc(text: str) -> float:
    """Parse an ISO-8601 timestamp that carries an explicit UTC offset to epoch seconds."""
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no UTC offset")
    return parsed.timestamp()


class WallClock:
    """Host time. The sole place the process reads its own clock."""

    def now(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()

    def utc_iso(self) -> str:
        return format_ts_utc(self.now())

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    @asynccontextmanager
    async def timeout(self, seconds: float) -> AsyncIterator[None]:
        async with asyncio.timeout(seconds):
            yield


@dataclass(order=True)
class _Timer:
    when: float
    seq: int
    fire: Callable[[], None] = field(compare=False)
    active: bool = field(default=True, compare=False)


class FixtureClock:
    """Virtual time that never reads the host clock.

    Time moves only when the replay runner calls `advance_to(ts)` with the next fixture
    timestamp. Sleep and timeout deadlines sit in one heap and fire in `(when, seq)`
    order, so scheduling does not depend on asyncio internals or host CPU speed.
    """

    def __init__(self, start: float = 0.0) -> None:
        self._now = start
        self._timers: list[_Timer] = []
        self._seq = itertools.count()

    def now(self) -> float:
        return self._now

    def monotonic(self) -> float:
        return self._now

    def utc_iso(self) -> str:
        return format_ts_utc(self._now)

    def advance_to(self, ts: float) -> None:
        """Move virtual time forward to `ts`, firing every timer due on the way."""
        if ts < self._now:
            raise ValueError("virtual time cannot move backwards")
        while self._timers and self._timers[0].when <= ts:
            timer = heapq.heappop(self._timers)
            if not timer.active:
                continue
            self._now = timer.when
            timer.active = False
            timer.fire()
        self._now = ts

    def _schedule(self, delay: float, fire: Callable[[], None]) -> _Timer:
        if delay < 0:
            raise ValueError("delay must be non-negative")
        timer = _Timer(self._now + delay, next(self._seq), fire)
        heapq.heappush(self._timers, timer)
        return timer

    async def yield_to_loop(self) -> None:
        """Yield once so peer seat tasks run between fixture events.

        The single sanctioned suspension outside a timed wait: the runner is
        synchronous, so virtual time does not advance here; the next
        ``advance_to`` still fires every due timer in heap order.
        """
        await asyncio.sleep(0)

    async def sleep(self, seconds: float) -> None:
        """Suspend until virtual time reaches now + seconds (via `advance_to`)."""
        waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        def wake() -> None:
            if not waiter.done():
                waiter.set_result(None)

        self._schedule(seconds, wake)
        await waiter

    @asynccontextmanager
    async def timeout(self, seconds: float) -> AsyncIterator[None]:
        """Cancel the current task and raise TimeoutError when virtual time passes the deadline."""
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("timeout requires a running task")
        expired = False
        handled = False

        def expire() -> None:
            nonlocal expired
            expired = True
            task.cancel()

        timer = self._schedule(seconds, expire)
        try:
            yield
        except asyncio.CancelledError:
            if expired:
                handled = True
                task.uncancel()
                raise TimeoutError from None
            raise
        finally:
            timer.active = False
            if expired and not handled:
                task.uncancel()
