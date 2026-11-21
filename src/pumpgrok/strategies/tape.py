"""Read-only market tape handed to strategies (STR-01).

A :class:`Tape` is an immutable snapshot of ticks in non-decreasing time
order. Strategies read it through the frozen :class:`Tick` and the
tuple snapshot; there is no append, no item assignment, and no attribute
write (the dataclass is frozen, so mutation raises
``FrozenInstanceError`` and the tuple has no mutators). Money fields are
integer lamports.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Tape", "Tick"]


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
