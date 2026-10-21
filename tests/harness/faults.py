"""Deterministic degraded-mode injection over replay fixture events.

Each mode fires at one event index so a test can place the fault exactly. Injected
errors subclass `InjectedFault`, so a product error can never be mistaken for one.
`TIMEOUT` raises the builtin `TimeoutError`, the type product code must already handle.
"""

from __future__ import annotations

import errno
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import IO, Any

from pumpgrok.replay.clock import format_ts_utc, parse_ts_utc


class FaultMode(StrEnum):
    STALE = "stale"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    RAISE = "raise"
    UNWRITABLE = "unwritable"


class InjectedFault(RuntimeError):
    """Raised by FaultMode.RAISE."""


class InjectedRateLimit(InjectedFault):
    """Raised by FaultMode.RATE_LIMIT; mirrors an HTTP 429 with a retry hint."""

    status = 429

    def __init__(self, retry_after_s: float) -> None:
        super().__init__("injected rate limit")
        self.retry_after_s = retry_after_s


class FaultInjector:
    """Apply one fault at `at_index` of an event stream, or to a write sink.

    STALE rewinds that event's `ts_utc` by `stale_by_s` and marks it `fault: stale`, so
    freshness checks downstream see old data. TIMEOUT, RATE_LIMIT and RAISE raise at
    that index after the earlier events have been yielded. UNWRITABLE leaves events
    untouched and makes `open_sink` fail with EACCES.
    """

    def __init__(
        self,
        mode: FaultMode,
        *,
        at_index: int = 0,
        stale_by_s: float = 3600.0,
        retry_after_s: float = 1.0,
    ) -> None:
        if at_index < 0:
            raise ValueError("at_index must be non-negative")
        self._mode = mode
        self._at = at_index
        self._stale_by_s = stale_by_s
        self._retry_after_s = retry_after_s

    @property
    def mode(self) -> FaultMode:
        return self._mode

    def apply(self, events: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        for index, event in enumerate(events):
            if index != self._at:
                yield event
                continue
            if self._mode is FaultMode.STALE:
                stale = dict(event)
                stamp = parse_ts_utc(str(event["ts_utc"])) - self._stale_by_s
                stale["ts_utc"] = format_ts_utc(stamp)
                stale["fault"] = FaultMode.STALE.value
                yield stale
            elif self._mode is FaultMode.TIMEOUT:
                raise TimeoutError("injected upstream timeout")
            elif self._mode is FaultMode.RATE_LIMIT:
                raise InjectedRateLimit(self._retry_after_s)
            elif self._mode is FaultMode.RAISE:
                raise InjectedFault("injected fault")
            else:
                yield event

    @contextmanager
    def open_sink(self, path: Path) -> Iterator[IO[str]]:
        """Open `path` for appending, or fail with EACCES in UNWRITABLE mode."""
        if self._mode is FaultMode.UNWRITABLE:
            raise PermissionError(errno.EACCES, "injected: sink is unwritable", str(path))
        with path.open("a", encoding="utf-8") as fh:
            yield fh
