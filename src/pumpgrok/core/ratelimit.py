"""Token-bucket rate limiter on the injected clock.

Port of the vendor ``ops.py`` ``RateLimiter``. Logic is 1:1; the only
difference is time: the vendor defaults to ``time.monotonic`` while this
module takes the reading from an injected ``Clock`` (no default-argument
clocks anywhere in this codebase), and waits run on ``clock.sleep`` so a
replay never blocks on wall time.
"""

from __future__ import annotations

import asyncio

from pumpgrok.replay.clock import Clock


class RateLimiter:
    """At most ``per_minute`` calls, with a burst up to ``burst``.

    Tokens refill continuously; ``acquire`` waits on the injected clock
    until a token is available and returns how long it waited.
    """

    def __init__(self, per_minute: float, burst: float | None, clock: Clock) -> None:
        self.rate = max(0.001, per_minute) / 60.0
        self.capacity = burst if burst is not None else max(1.0, per_minute / 6.0)
        self._clock = clock
        self.tokens = self.capacity
        self.updated = clock.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self._clock.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now

    def delay_for_next(self) -> float:
        """Seconds until the next call is allowed. 0 means call now."""
        self._refill()
        if self.tokens >= 1.0:
            return 0.0
        return (1.0 - self.tokens) / self.rate

    async def acquire(self) -> float:
        """Wait for the right to call. Returns how long was waited."""
        waited = 0.0
        async with self._lock:
            while True:
                delay = self.delay_for_next()
                if delay <= 0:
                    self.tokens -= 1.0
                    return waited
                waited += delay
                await self._clock.sleep(delay)
