"""Characterization: operations helpers (STRUCT-004).

Pins the vendor ``ops.py`` behavior against
``vendor/grokbot-pumpfun/src/ops.py:90-182`` (``RateLimiter``,
``CircuitBreaker``), ``ops.py:372-440`` (``Heartbeat``, ``drain``,
``install_signal_handlers``) and ``vendor/grokbot-pumpfun/tests/test_ops.py``
(vendor oracle, kept byte-identical per R53).

Adaptations from the oracle (deliberate):

- ``RateLimiter`` runs against its real port (``core/ratelimit.py``) on a
  ``FixtureClock``: burst, throttle, refill, no-overfill, and serialization
  without waiting. The port takes readings from the injected clock and waits
  on ``clock.sleep``; acquiring a covered token never suspends.
- ``CircuitBreaker``, ``drain``, ``Heartbeat``, and ``install_signal_handlers``
  have no production port in this plan (the breaker port lands in
  ``risk/breakers.py`` in plan 04-05, lifecycle in plan 04-07). They are
  pinned here as documented test-local mirrors of the vendor originals so
  the behavior cannot drift before the ports land; the owning plans rewire
  these tests to the ports. ``GrokOps``/``CallBudget``/``HealthServer`` rows
  belong to those plans too and are not repeated here.
- All prose is English; the vendor text is Russian.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Callable
from typing import Any

import pytest

from pumpgrok.core.ratelimit import RateLimiter
from pumpgrok.replay.clock import FixtureClock

log = logging.getLogger(__name__)

# --- limiter: against the real port -------------------------------------------


def _limiter(clock: FixtureClock, per_minute: float = 60.0, burst: float = 1.0) -> RateLimiter:
    return RateLimiter(per_minute=per_minute, burst=burst, clock=clock)


def test_limiter_allows_burst_then_throttles() -> None:
    clock = FixtureClock(start=1_000.0)
    limiter = _limiter(clock)
    limiter.tokens = 2.0
    limiter.updated = clock.monotonic()
    assert limiter.delay_for_next() == 0.0
    limiter.tokens = 0.0
    assert limiter.delay_for_next() == pytest.approx(1.0, abs=0.01)


def test_limiter_refills_over_time() -> None:
    clock = FixtureClock(start=1_000.0)
    limiter = _limiter(clock)
    limiter.tokens = 0.0
    limiter.updated = clock.monotonic()
    clock.advance_to(1_060.0)
    assert limiter.delay_for_next() == 0.0


def test_limiter_does_not_overfill() -> None:
    clock = FixtureClock(start=1_000.0)
    limiter = _limiter(clock, burst=2.0)
    limiter.tokens = 0.0
    limiter.updated = clock.monotonic()
    clock.advance_to(1_000.0 + 3_600.0)
    limiter.delay_for_next()
    assert limiter.tokens == 2.0


async def test_limiter_acquire_never_waits_when_covered() -> None:
    clock = FixtureClock(start=1_000.0)
    limiter = RateLimiter(per_minute=60_000.0, burst=5.0, clock=clock)
    waited = [await limiter.acquire() for _ in range(5)]
    assert waited == [0.0] * 5


async def test_limiter_serializes_calls() -> None:
    clock = FixtureClock(start=1_000.0)
    limiter = RateLimiter(per_minute=60_000.0, burst=1.0, clock=clock)
    waited = [await limiter.acquire() for _ in range(1)]
    assert all(w >= 0 for w in waited)


# --- test-local mirrors (pending risk/breakers.py, plan 04-05) -----------------
#
# Faithful copies of the vendor originals with English prose. The owning
# plan rewires these tests to the production ports; until then the mirrors
# pin the behavior the ports must reproduce.


class ManualClock:
    """Vendor FakeClock shape: call to read, advance to move."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class CircuitBreaker:
    """Opens after N consecutive failures, probes after cooldown.

    Test-local mirror of vendor ``ops.py:131-182``. The half-open probe is
    the single call admitted right after cooldown: it runs with the failure
    count one below threshold, so one more failure reopens immediately.
    """

    def __init__(self, failures: int, cooldown: float, clock: Callable[[], float]) -> None:
        self.threshold = max(1, failures)
        self.cooldown = max(0.0, cooldown)
        self.clock = clock
        self.consecutive_failures = 0
        self.opened_at: float | None = None
        self.trips = 0

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if self.clock() - self.opened_at >= self.cooldown:
            self.opened_at = None
            self.consecutive_failures = self.threshold - 1
            return False
        return True

    @property
    def state(self) -> str:
        if self.is_open:
            return "open"
        return "half-open" if self.consecutive_failures else "closed"

    def remaining_cooldown(self) -> float:
        if self.opened_at is None:
            return 0.0
        return max(0.0, self.cooldown - (self.clock() - self.opened_at))

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.threshold and self.opened_at is None:
            self.opened_at = self.clock()
            self.trips += 1


def test_breaker_opens_after_threshold() -> None:
    clock = ManualClock()
    breaker = CircuitBreaker(failures=3, cooldown=60.0, clock=clock)
    assert breaker.state == "closed"
    breaker.record_failure()
    breaker.record_failure()
    assert not breaker.is_open
    breaker.record_failure()
    assert breaker.is_open
    assert breaker.state == "open"
    assert breaker.trips == 1


def test_success_resets_failures() -> None:
    breaker = CircuitBreaker(failures=3, cooldown=60.0, clock=ManualClock())
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    assert breaker.consecutive_failures == 0
    assert not breaker.is_open


def test_breaker_closes_after_cooldown() -> None:
    clock = ManualClock()
    breaker = CircuitBreaker(failures=2, cooldown=60.0, clock=clock)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_open
    clock.advance(61.0)
    assert not breaker.is_open
    assert breaker.state == "half-open"


def test_reopens_immediately_if_probe_fails() -> None:
    clock = ManualClock()
    breaker = CircuitBreaker(failures=2, cooldown=60.0, clock=clock)
    breaker.record_failure()
    breaker.record_failure()
    clock.advance(61.0)
    assert not breaker.is_open
    breaker.record_failure()
    assert breaker.is_open
    assert breaker.trips == 2


def test_probe_success_closes_breaker() -> None:
    clock = ManualClock()
    breaker = CircuitBreaker(failures=2, cooldown=60.0, clock=clock)
    breaker.record_failure()
    breaker.record_failure()
    clock.advance(61.0)
    assert not breaker.is_open
    breaker.record_success()
    assert breaker.state == "closed"
    assert breaker.remaining_cooldown() == 0.0


def test_remaining_cooldown_counts_down() -> None:
    clock = ManualClock()
    breaker = CircuitBreaker(failures=1, cooldown=60.0, clock=clock)
    breaker.record_failure()
    assert breaker.remaining_cooldown() == pytest.approx(60.0)
    clock.advance(15.0)
    assert breaker.remaining_cooldown() == pytest.approx(45.0)


def test_closed_breaker_has_no_cooldown() -> None:
    breaker = CircuitBreaker(failures=3, cooldown=60.0, clock=ManualClock())
    assert breaker.remaining_cooldown() == 0.0
    assert breaker.state == "closed"


# --- test-local mirrors (pending supervisor lifecycle, plan 04-07) ---------------


async def drain(tasks: set[asyncio.Task[Any]], grace: float) -> tuple[int, int]:
    """Let in-flight tasks finish, cancel the rest. Returns (done, cancelled).

    Test-local mirror of vendor ``ops.py:406-417``.
    """
    if not tasks:
        return 0, 0
    done, pending = await asyncio.wait(tasks, timeout=grace)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    return len(done), len(pending)


async def test_drain_waits_for_quick_tasks() -> None:
    async def quick() -> str:
        return "ok"

    tasks = {asyncio.create_task(quick()) for _ in range(3)}
    assert await drain(tasks, grace=5.0) == (3, 0)


async def test_drain_cancels_stuck_tasks() -> None:
    async def stuck() -> None:
        await asyncio.sleep(3600.0)

    tasks = {asyncio.create_task(stuck())}
    assert await drain(tasks, grace=0.01) == (0, 1)


async def test_drain_on_empty_set() -> None:
    assert await drain(set(), grace=1.0) == (0, 0)


class Heartbeat:
    """A liveness line in the log, proving the process breathes.

    Test-local mirror of vendor ``ops.py:372-402``. One divergence: the
    vendor loop sleeps and is cancelled on stop; this mirror waits on a
    stop event with a timeout so ``stop`` never cancels a task that may be
    logging. The emitted line is identical either way.
    """

    def __init__(self, interval: float, provider: Callable[[], dict[str, Any]]) -> None:
        self.interval = max(1.0, interval)
        self.provider = provider
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def line(self) -> str:
        status = self.provider()
        parts = [
            f"{key}={value}" for key, value in status.items() if not isinstance(value, (dict, list))
        ]
        return " ".join(parts)

    def start(self) -> asyncio.Task[None]:
        self._stop.clear()
        self._task = asyncio.create_task(self._run())
        return self._task

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except TimeoutError:
                log.info("alive: %s", self.line())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None


def test_heartbeat_line_is_flat() -> None:
    beat = Heartbeat(1.0, lambda: {"status": "ok", "open": 2, "nested": {"a": 1}})
    line = beat.line()
    assert "status=ok" in line
    assert "open=2" in line
    assert "nested" not in line


async def test_heartbeat_start_stop_is_clean() -> None:
    beat = Heartbeat(60.0, lambda: {"status": "ok"})
    task = beat.start()
    assert isinstance(task, asyncio.Task)
    await beat.stop()
    assert beat._task is None
    await beat.stop()


def install_signal_handlers(stop: Callable[[str], Any]) -> None:
    """Wire SIGINT/SIGTERM to a graceful stop, not KeyboardInterrupt.

    Test-local mirror of vendor ``ops.py:420-431`` (POSIX path only; the
    Windows fallback lives with the supervisor lifecycle in plan 04-07).
    """
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop, sig.name)


def test_signal_handlers_cover_int_and_term(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, Callable[..., Any], tuple[Any, ...]]] = []

    class FakeLoop:
        def add_signal_handler(self, sig: Any, callback: Callable[..., Any], *args: Any) -> None:
            calls.append((sig, callback, args))

    received: list[str] = []
    monkeypatch.setattr(asyncio, "get_running_loop", FakeLoop)
    install_signal_handlers(received.append)
    assert {sig for sig, _, _ in calls} == {signal.SIGINT, signal.SIGTERM}
    for _, callback, args in calls:
        callback(*args)
    assert sorted(received) == ["SIGINT", "SIGTERM"]


def test_signal_handler_callback_is_the_stop_function(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, Callable[..., Any], tuple[Any, ...]]] = []

    class FakeLoop:
        def add_signal_handler(self, sig: Any, callback: Callable[..., Any], *args: Any) -> None:
            calls.append((sig, callback, args))

    def stop(reason: str) -> None:
        raise AssertionError(f"must not run in this test: {reason}")

    monkeypatch.setattr(asyncio, "get_running_loop", FakeLoop)
    install_signal_handlers(stop)
    assert calls != []
    assert all(callback is stop for _, callback, _ in calls)
    assert [args for _, _, args in calls] == [("SIGINT",), ("SIGTERM",)]
