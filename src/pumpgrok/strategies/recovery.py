"""Baseline strategy state and restart recovery: tapes, peaks and probation (RT-04, library half).

A baseline strategy carries one StrategyBook. It holds the strategy's per-mint price tape, its
open positions, the peak price of each open position, and the probation count: how many entries
the strategy has made in each mint. save_state writes the book to the strategy_state sidecar
(ledger/strategy_state.py, one row per strategy id); restore_state reads it back and replaces the
strategy's book. A row whose body no longer matches its hash is refused on read.

Peaks are bookkeeping: the baseline exit rules read entry prices, not peaks. The launch sniper
reads probation to enter each mint once. exact() reads a float parameter or tick value by its
shortest decimal form, so every rule comparison is exact rational arithmetic.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, ClassVar, Protocol

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.strategy_state import read_state, write_state
from pumpgrok.strategies.base import TapePoint
from pumpgrok.strategies.tape import DEFAULT_TAPE_CAPACITY, Tape

__all__ = [
    "BookedStrategy",
    "Position",
    "StrategyBook",
    "exact",
    "restore_state",
    "save_state",
]


def exact(value: float | int) -> Fraction:
    """A parameter or tick value as an exact rational: floats by their shortest decimal form."""
    if isinstance(value, bool):
        raise TypeError("a boolean is not a strategy value")
    return Fraction(value) if isinstance(value, int) else Fraction(repr(value))


def _int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int")
    return value


@dataclass(frozen=True)
class Position:
    """An open position. Prices and sizes are integer lamports; the entry time is epoch seconds."""

    entry_ts: float
    entry_price_lamports: int
    size_lamports: int


@dataclass
class StrategyBook:
    """Everything a baseline strategy must carry across a restart."""

    tape: Tape
    positions: dict[str, Position] = field(default_factory=dict)
    peaks: dict[str, int] = field(default_factory=dict)
    probation: dict[str, int] = field(default_factory=dict)

    @classmethod
    def fresh(cls) -> StrategyBook:
        return cls(tape=Tape(capacity=DEFAULT_TAPE_CAPACITY))

    def window(self, mint: str, now: float, seconds: float) -> tuple[TapePoint, ...]:
        """The mint's recorded points no older than `seconds` before `now`, oldest first."""
        return tuple(point for point in self.tape.points(mint) if point.ts >= now - seconds)

    def observe(self, mint: str, ts: float, price_lamports: int) -> None:
        """Record one tick on the tape and raise the peak of an open position."""
        self.tape.record(mint, TapePoint(ts=ts, price_lamports=price_lamports))
        if mint in self.positions:
            self.peaks[mint] = max(self.peaks[mint], price_lamports)

    def open(self, mint: str, position: Position) -> None:
        """Open a position in the mint and count the entry toward its probation."""
        if mint in self.positions:
            raise ValueError(f"a position is already open in {mint}")
        self.positions[mint] = position
        self.peaks[mint] = position.entry_price_lamports
        self.probation[mint] = self.probation.get(mint, 0) + 1

    def close(self, mint: str) -> Position:
        """Close the mint's position and return it."""
        self.peaks.pop(mint, None)
        return self.positions.pop(mint)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tape": self.tape.to_dict(),
            "positions": {
                mint: {
                    "entry_ts": position.entry_ts,
                    "entry_price_lamports": position.entry_price_lamports,
                    "size_lamports": position.size_lamports,
                }
                for mint, position in sorted(self.positions.items())
            },
            "peaks": dict(sorted(self.peaks.items())),
            "probation": dict(sorted(self.probation.items())),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StrategyBook:
        positions = {
            str(mint): Position(
                entry_ts=float(raw["entry_ts"]),
                entry_price_lamports=_int(raw["entry_price_lamports"], "entry price"),
                size_lamports=_int(raw["size_lamports"], "position size"),
            )
            for mint, raw in data["positions"].items()
        }
        peaks = {str(mint): _int(value, "peak") for mint, value in data["peaks"].items()}
        probation = {
            str(mint): _int(value, "probation") for mint, value in data["probation"].items()
        }
        return cls(
            tape=Tape.from_dict(data["tape"]),
            positions=positions,
            peaks=peaks,
            probation=probation,
        )


class BookedStrategy(Protocol):
    """A strategy that carries a StrategyBook across a restart."""

    strategy_id: ClassVar[str]
    book: StrategyBook


def save_state(store: LedgerStore, strategy: BookedStrategy) -> str:
    """Write the strategy's book to strategy_state; returns the stored state hash."""
    return write_state(store, strategy.strategy_id, strategy.book.to_dict())


def restore_state(store: LedgerStore, strategy: BookedStrategy) -> bool:
    """Replace the strategy's book with the stored one. False when no state was saved."""
    data = read_state(store, strategy.strategy_id)
    if data is None:
        return False
    strategy.book = StrategyBook.from_dict(data)
    return True
