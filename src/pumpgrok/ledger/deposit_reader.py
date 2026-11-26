"""Read-only view of the position_deposits sidecar, keyed by PositionOpened seq.

The reader lives in the ledger package with no execution imports, so the ledger, the risk
engine and the supervisor can fold deposits without importing the execution package (which
imports the risk engine and would cycle). The writer stays in execution/deposits.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

    from pumpgrok.ledger.store import LedgerStore

__all__ = ["position_deposits_by_seq"]


def _table_exists(db: sqlite3.Connection) -> bool:
    row = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'position_deposits';"
    ).fetchone()
    return row is not None


def position_deposits_by_seq(store: LedgerStore) -> dict[int, int]:
    """The deposit recorded against each PositionOpened seq; empty when none was recorded."""
    db = store._db
    if not _table_exists(db):
        return {}
    rows = db.execute(
        "SELECT opened_seq, deposit_lamports FROM position_deposits ORDER BY opened_seq;"
    )
    return {int(seq): int(lamports) for seq, lamports in rows.fetchall()}
