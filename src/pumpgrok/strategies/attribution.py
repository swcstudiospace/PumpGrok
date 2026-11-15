"""Per-strategy P&L attribution folded from the ledger, against the desk total (STR-03).

The desk total is the ledger's own net: the reducer folds every row from the opening equity
recorded in the ledger's meta, and equity.net_lamports values the window. Money is integer
lamports throughout.
"""

from __future__ import annotations

from pumpgrok.backtest.equity import net_lamports
from pumpgrok.ledger.reducer import LedgerState, initial_state
from pumpgrok.ledger.store import LedgerStore

__all__ = ["AttributionError", "desk_genesis", "desk_net_lamports"]


class AttributionError(ValueError):
    """The ledger cannot be folded for attribution: its opening equity is missing or wrong."""


def desk_genesis(store: LedgerStore) -> LedgerState:
    """The ledger's opening state, from the initial equity recorded in its meta."""
    meta = store.get_meta("initial_equity_lamports")
    if meta is None:
        raise AttributionError("ledger holds no initial_equity_lamports meta")
    return initial_state(source="replay", initial_equity_lamports=int(meta), day_utc="")


def desk_net_lamports(store: LedgerStore) -> int:
    """The desk's net realized lamports over every row of the ledger."""
    return net_lamports(desk_genesis(store), store.read(limit=None))
