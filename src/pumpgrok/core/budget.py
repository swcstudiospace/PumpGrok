"""Daily Grok call budget on the injected clock.

Port of the vendor ``ops.py`` ``CallBudget``. Logic is 1:1; the only
difference is time: the vendor defaults to ``time.time`` while this module
reads the day from an injected ``Clock`` (no default-argument clocks
anywhere in this codebase), so the UTC-midnight rollover is replayable.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pumpgrok.replay.clock import Clock


def utc_day(timestamp: float) -> str:
    """Calendar day of an epoch timestamp in UTC, ``YYYY-MM-DD``."""
    return datetime.fromtimestamp(timestamp, tz=UTC).strftime("%Y-%m-%d")


class CallBudget:
    """Ceiling on Grok calls per UTC day. Resets itself at midnight."""

    def __init__(self, max_per_day: int, clock: Clock, spent: int = 0) -> None:
        self.max_per_day = max(1, max_per_day)
        self._clock = clock
        self.day = utc_day(clock.now())
        self.spent = spent
        self._warned = False

    def _roll(self) -> None:
        today = utc_day(self._clock.now())
        if today != self.day:
            self.day = today
            self.spent = 0
            self._warned = False

    @property
    def remaining(self) -> int:
        """Calls still allowed today."""
        self._roll()
        return max(0, self.max_per_day - self.spent)

    def try_spend(self, amount: int = 1) -> bool:
        """Take ``amount`` calls from today. False leaves the budget untouched."""
        self._roll()
        if self.spent + amount > self.max_per_day:
            return False
        self.spent += amount
        return True
