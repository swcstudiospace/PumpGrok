"""Shared window valuation for backtests: the one definition of equity and net (BT-05, BT-07).

Equity is cash plus every open position, each valued at its recorded mark or,
when no mark is recorded, at its cost basis. A purchase therefore moves cash
and position value together and never reads as a loss. Net is the closing
equity of a window less its opening equity. The backtest report and the search
selection both call this module, so they cannot disagree about the same
ledger. Money stays integer lamports.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pumpgrok.ledger.reducer import LedgerState, reduce

__all__ = ["equity_lamports", "net_lamports"]


def equity_lamports(state: LedgerState) -> int:
    """Cash plus open positions, each at its recorded mark or else at cost.

    The reducer marks a position at last_mtm_lamports, which stays zero until
    the first mark, so a fresh purchase would read as a loss of its whole
    cost. A position with no recorded mark is held at its cost basis instead,
    which keeps buy cash outflows out of trading PnL.
    """
    total = state.cash_lamports
    for pos in state.positions.values():
        if pos.token_units <= 0:
            continue
        total += pos.last_mtm_lamports if pos.last_mtm_ts_utc else pos.cost_basis_lamports
    return total


def net_lamports(genesis: LedgerState, rows: Sequence[Mapping[str, Any]]) -> int:
    """Closing equity of the window less its opening equity, folding rows in order.

    genesis is the window's opening state. Each row folds through the reducer,
    so fills carry their cash delta and refusals their fees, each counted once.
    A window with no rows nets 0.
    """
    state = genesis
    for row in rows:
        state = reduce(state, row)
    return equity_lamports(state) - equity_lamports(genesis)
