<<<<<<< HEAD
"""Read-only market tape handed to strategies (STR-01).

A :class:`Tape` is an immutable snapshot of ticks in non-decreasing time
order. Strategies read it through the frozen :class:`Tick` and the
tuple snapshot; there is no append, no item assignment, and no attribute
write (the dataclass is frozen, so mutation raises
``FrozenInstanceError`` and the tuple has no mutators). Money fields are
integer lamports.
=======
"""Bounded per-strategy price tape, JSON-serialisable for recovery (STR-03).

Each strategy owns one Tape. Each mint keeps its last ``capacity`` points, oldest first.
Prices are integer lamports; timestamps are epoch seconds and never go back in time for
one mint. The JSON form sorts its keys and refuses NaN and infinity. Money never passes
through a float here.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

import json
<<<<<<< HEAD
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Tape", "Tick", "load_tape"]


@dataclass(frozen=True)
class Tick:
    """One market tick: epoch seconds, mint, integer price, buyers, age."""

    ts: float
    mint: str
    price_lamports: int
    buyers: int = 0
    created_ts: float | None = None
    curve_progress: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.price_lamports, bool) or not isinstance(self.price_lamports, int):
            raise ValueError("price_lamports must be integer lamports")
        if not self.mint:
            raise ValueError("a Tick names a mint")

    @property
    def age_seconds(self) -> float:
        """Age of the mint at this tick; 0.0 when creation time is unknown."""
        if self.created_ts is None:
            return 0.0
        return max(0.0, self.ts - self.created_ts)


@dataclass(frozen=True)
class Tape:
    """Immutable tick sequence in non-decreasing time order."""

    ticks: tuple[Tick, ...] = ()

    def __post_init__(self) -> None:
        previous = float("-inf")
        for tick in self.ticks:
            if tick.ts < previous:
                raise ValueError("tape ticks must be in non-decreasing ts order")
            previous = tick.ts

    @classmethod
    def from_ticks(cls, ticks: list[Tick] | tuple[Tick, ...]) -> Tape:
        """Build a tape; the caller's list is copied into a tuple."""
        return cls(ticks=tuple(ticks))

    def __len__(self) -> int:
        return len(self.ticks)

    def ticks_for(self, mint: str) -> tuple[Tick, ...]:
        """Ticks for one mint in order (read-only snapshot)."""
        return tuple(tick for tick in self.ticks if tick.mint == mint)


def load_tape(dataset_dir: str | Path) -> Tape:
    """Load a recorded tape fixture (ticks.json, ticks only) unchanged.

    The fixture directory holds ``ticks.json`` (a list of tick objects in
    non-decreasing ts order) and ``manifest.json``. The runtime consumes
    the ticks exactly as recorded; no fill or order lives in the fixture.
    """
    base = Path(dataset_dir)
    raw = json.loads((base / "ticks.json").read_text(encoding="utf-8"))
    ticks: list[Tick] = []
    for item in raw["ticks"]:
        ticks.append(
            Tick(
                ts=float(item["ts"]),
                mint=str(item["mint"]),
                price_lamports=int(item["price_lamports"]),
                buyers=int(item.get("buyers", 0)),
                created_ts=(None if item.get("created_ts") is None else float(item["created_ts"])),
                curve_progress=float(item.get("curve_progress", 0.0)),
            )
        )
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    if "dataset" in manifest and not isinstance(manifest["dataset"], str):
        raise ValueError("tape manifest dataset must be a str")
    return Tape.from_ticks(ticks)
=======
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
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
