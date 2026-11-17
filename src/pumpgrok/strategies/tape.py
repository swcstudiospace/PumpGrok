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

DEFAULT_TAPE_CAPACITY = 64


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
