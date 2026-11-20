"""Bounded per-strategy price tape, JSON-serialisable for recovery (STR-03).

Each strategy owns one Tape. Each mint keeps its last ``capacity`` points, oldest first.
Prices are integer lamports; timestamps are epoch seconds and never go back in time for
one mint. The JSON form sorts its keys and refuses NaN and infinity. Money never passes
through a float here.
"""

from __future__ import annotations

import json
import math
from collections import deque
from collections.abc import Mapping
from typing import Any

from pumpgrok.strategies.base import TapePoint

__all__ = ["DEFAULT_TAPE_CAPACITY", "Tape", "TapeError"]

# EXEC-EX-10: sized to the largest lookback (7200 s at ~1 tick/s) so a window
# with more than 64 ticks is never truncated by count mid-window.
DEFAULT_TAPE_CAPACITY = 8192

# EXEC-EX-42: bounds distinct mints for long soak runs (LRU by last record).
_MAX_MINTS = 4096


class TapeError(ValueError):
    """A tape point, capacity or serialised form is malformed."""


def _check_point(point: TapePoint) -> None:
    if isinstance(point.price_lamports, bool) or not isinstance(point.price_lamports, int):
        raise TapeError("tape price must be an int number of lamports")
    if point.price_lamports < 0:
        raise TapeError("tape price must not be negative")
    if isinstance(point.ts, bool) or not isinstance(point.ts, int | float):
        raise TapeError("tape timestamp must be a number of epoch seconds")
    if not math.isfinite(point.ts):
        raise TapeError("tape timestamp must be finite")


class Tape:
    """Recent prices per mint, bounded, with a deterministic JSON form."""

    def __init__(self, capacity: int = DEFAULT_TAPE_CAPACITY) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
            raise TapeError("tape capacity must be a positive int")
        self._capacity = capacity
        self._series: dict[str, deque[TapePoint]] = {}
        self._last_seen: dict[str, float] = {}

    @property
    def capacity(self) -> int:
        return self._capacity

    def record(self, mint: str, point: TapePoint) -> None:
        """Append one point for a mint, dropping the oldest once the bound is reached."""
        _check_point(point)
        series = self._series.setdefault(mint, deque(maxlen=self._capacity))
        if series and point.ts < series[-1].ts:
            raise TapeError("tape points must not go back in time for one mint")
        series.append(point)
        # EXEC-EX-42: evict the least-recently-recorded mint past the cap.
        self._last_seen[mint] = point.ts
        while len(self._series) > _MAX_MINTS:
            oldest = min(self._last_seen, key=self._last_seen.__getitem__)
            self._series.pop(oldest, None)
            self._last_seen.pop(oldest, None)

    def points(self, mint: str) -> tuple[TapePoint, ...]:
        """The mint's recorded points, oldest first; empty when none were recorded."""
        return tuple(self._series.get(mint, ()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "capacity": self._capacity,
            "mints": {
                mint: [{"ts": point.ts, "price_lamports": point.price_lamports} for point in series]
                for mint, series in sorted(self._series.items())
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Tape:
        tape = cls(capacity=data["capacity"])
        for mint, series in data["mints"].items():
            for raw in series:
                tape.record(
                    str(mint),
                    TapePoint(ts=raw["ts"], price_lamports=raw["price_lamports"]),
                )
        return tape

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, text: str) -> Tape:
        return cls.from_dict(json.loads(text))
