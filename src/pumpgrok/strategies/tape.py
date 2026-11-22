"""Read-only market tape handed to strategies (STR-01).

A :class:`Tape` is an immutable snapshot of ticks in non-decreasing time
order. Strategies read it through the frozen :class:`Tick` and the
tuple snapshot; there is no append, no item assignment, and no attribute
write (the dataclass is frozen, so mutation raises
``FrozenInstanceError`` and the tuple has no mutators). Money fields are
integer lamports.
"""

from __future__ import annotations

import json
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
                created_ts=(
                    None if item.get("created_ts") is None else float(item["created_ts"])
                ),
                curve_progress=float(item.get("curve_progress", 0.0)),
            )
        )
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    if "dataset" in manifest and not isinstance(manifest["dataset"], str):
        raise ValueError("tape manifest dataset must be a str")
    return Tape.from_ticks(ticks)
