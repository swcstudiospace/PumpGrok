"""Baseline strategy state and restart recovery: tapes, peaks and probation (RT-04, library half).

A baseline strategy carries one StrategyBook. It holds the strategy's per-mint price tape, its
open positions, the peak price of each open position, and the probation count: how many entries
the strategy has made in each mint. save_state writes the book to the strategy_state sidecar
(ledger/strategy_state.py, one row per strategy id); restore_state reads it back and replaces the
strategy's book. A row whose body no longer matches its hash is refused on read.

restore_from_ledger rebuilds probation and the open mints from the ledger rows alone, so a restart
still refuses a second entry into a mint already entered. The ledger holds no tapes or exact peaks;
those come only from strategy_state.

Peaks are bookkeeping: the baseline exit rules read entry prices, not peaks. The launch sniper
reads probation to enter each mint once. exact() reads a float parameter or tick value by its
shortest decimal form, so every rule comparison is exact rational arithmetic.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, ClassVar, Protocol

from pumpgrok.ledger.reducer import PositionView, initial_state, reduce
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.strategy_state import read_state, write_state
from pumpgrok.ledger.ticket_refs import load_refs
from pumpgrok.strategies.base import TapePoint
from pumpgrok.strategies.tape import DEFAULT_TAPE_CAPACITY, Tape

__all__ = [
    "BookedStrategy",
    "LedgerStrategyState",
    "Position",
    "StrategyBook",
    "desk_watch_set",
    "exact",
    "ledger_strategy_state",
    "restore_from_ledger",
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


@dataclass(frozen=True)
class LedgerStrategyState:
    """What the ledger alone proves about one strategy after a restart.

    ``probation`` counts the strategy's entries per mint: each PositionOpened row whose ticket is
    attributed to the strategy in strategy_ticket_refs. ``open_mints`` is the strategy's watch set:
    each mint with an open position in the fold whose ticket is attributed to the strategy.
    """

    strategy_id: str
    probation: dict[str, int]
    open_mints: frozenset[str]


def ledger_strategy_state(store: LedgerStore, strategy_id: str) -> LedgerStrategyState:
    """Rebuild the strategy's probation and open mints from the ledger rows alone.

    Counts fills, not intents: a buy the desk refused writes no PositionOpened row, while the live
    book counted it at intent time. The ledger keeps no structured record of a refused intent.
    """
    owned = {ticket for ticket, sid in load_refs(store).items() if sid == strategy_id}
    probation: dict[str, int] = {}
    for row in store.read(types=["PositionOpened"], limit=None):
        payload = row["payload"]
        if str(payload.get("ticket_id", "")) in owned:
            mint = str(payload["mint"])
            probation[mint] = probation.get(mint, 0) + 1
    open_views = _open_positions(store)
    open_mints = frozenset(mint for mint, view in open_views.items() if view.ticket_id in owned)
    return LedgerStrategyState(strategy_id=strategy_id, probation=probation, open_mints=open_mints)


def desk_watch_set(store: LedgerStore) -> frozenset[str]:
    """Every mint with an open position in the fold, desk-wide, whatever its ticket.

    TODO(owner): watch-set definition (index Finding 7). Default: every open position in the fold
    (token_units > 0). The bot-00 restart calls this; it is desk-wide, not per strategy.
    """
    return frozenset(_open_positions(store))


def _open_positions(store: LedgerStore) -> dict[str, PositionView]:
    """The fold's open positions (token_units > 0), keyed by mint."""
    state = initial_state(source="paper", initial_equity_lamports=0, day_utc="")
    for event in store.read(limit=None):
        state = reduce(state, event)
    return {mint: view for mint, view in state.positions.items() if view.token_units > 0}


def restore_from_ledger(store: LedgerStore, strategy: BookedStrategy) -> LedgerStrategyState:
    """Replace the strategy's probation with the ledger count and return the rebuilt state.

    Positions, peaks and the tape are left as they are: the ledger does not record them exactly.
    """
    rebuilt = ledger_strategy_state(store, strategy.strategy_id)
    strategy.book.probation = dict(rebuilt.probation)
    return rebuilt
