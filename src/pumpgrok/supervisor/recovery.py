"""Restart recovery: the state a desk holds again after a restart, rebuilt from the ledger (RT-04).

rebuild_desk_state reads the ledger and restores, for the desk as it stood when it stopped:

- each strategy's probation, from its PositionOpened rows and strategy_ticket_refs
  (restore_from_ledger), written into the strategy's book;
- the desk-wide watch set: every open position in the fold, whatever its ticket (desk_watch_set);
- each open position's exit deadline and exit peak (LedgerExitBook.sync, from the fold).

Tapes are not restored. Each strategy's tape starts empty, so a strategy with an empty tape makes
no decision until its window refills (owner decision 2026-11-18). Tape restore is Phase 18.

The rebuild reads the ledger and nothing else: it starts no timer, makes no Grok call and appends
no row. The watch set, the deadlines and the peaks are returned, not stored, because the exit
rules rebuild the same fold on every pass.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeGuard

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.strategies.base import Strategy
from pumpgrok.strategies.recovery import (
    BookedStrategy,
    StrategyBook,
    desk_watch_set,
    restore_from_ledger,
)
from pumpgrok.supervisor.exit_rules import LedgerExitBook

__all__ = ["RecoveredState", "rebuild_desk_state"]


@dataclass(frozen=True)
class RecoveredState:
    """What the desk holds again after a restart, rebuilt from the ledger alone."""

    #: strategy id -> mint -> the entries that strategy has made in that mint.
    probation: dict[str, dict[str, int]]
    #: every mint with an open position in the fold, desk-wide.
    watch_set: frozenset[str]
    #: mint -> epoch second at which the max-hold rule fires for that position.
    exit_deadlines: dict[str, float]
    #: mint -> exit peak, as a PRICE_SCALE integer.
    exit_peaks: dict[str, int]


def _has_book(strategy: Strategy) -> TypeGuard[BookedStrategy]:
    """Whether the strategy carries a StrategyBook, and so has probation to restore."""
    return isinstance(getattr(strategy, "book", None), StrategyBook)


def rebuild_desk_state(
    store: LedgerStore,
    strategies: Sequence[Strategy],
    exits: ExitsSettings,
) -> RecoveredState:
    """Rebuild the desk's ledger-held state for ``strategies`` under ``exits``.

    Probation is written into each strategy's book. The watch set, the exit deadlines and the exit
    peaks are read from the same fold the exit rules read, and returned.
    """
    probation: dict[str, dict[str, int]] = {}
    for strategy in strategies:
        if not _has_book(strategy):
            continue
        rebuilt = restore_from_ledger(store, strategy)
        probation[strategy.strategy_id] = dict(rebuilt.probation)
    book = LedgerExitBook(exits)
    book.sync(store)
    return RecoveredState(
        probation=probation,
        watch_set=desk_watch_set(store),
        exit_deadlines=book.exit_deadlines(),
        exit_peaks={mint: position.peak_price for mint, position in book.positions.items()},
    )
