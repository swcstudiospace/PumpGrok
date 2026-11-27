"""ATA deposits held as assets until their position closes, then refunded (FEE-01 deposit).

The first buy of a mint pays the ATA rent as a refundable deposit. The ledger row that opens
the position is unchanged in shape; its deposit is a fact of its own, written in the same
transaction through the ledger's sidecar hook, the way strategy_ticket_refs and strategy_state
are kept. The sidecar sits outside the hash chain and adds no event type or field.

A mint's deposit is the one recorded for its latest opening (seq order), so a reopened mint
carries only its current opening's deposit. A re-buy after a close pays no rent and records
zero. Legacy ledgers have no sidecar rows and therefore hold no deposit. A full close credits
the deposit back to cash once; a partial exit keeps it whole.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from pumpgrok.ledger.deposit_reader import position_deposits_by_seq

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore, SidecarWriter

__all__ = ["open_deposits", "opening_deposit_writer", "position_deposits_by_seq"]

_TABLE = "position_deposits"
_DDL = (
    "CREATE TABLE IF NOT EXISTS position_deposits ("
    " opened_seq INTEGER PRIMARY KEY,"
    " mint TEXT NOT NULL,"
    " deposit_lamports INTEGER NOT NULL);"
)


def opening_deposit_writer(mint: str, deposit_lamports: int) -> SidecarWriter:
    """Sidecar for the append of a buy that may open ``mint``.

    Records ``deposit_lamports`` against every PositionOpened row in the batch, inside the
    batch's own transaction, so the deposit commits or rolls back with its opening.
    """

    def write(db: sqlite3.Connection, stored: Sequence[Mapping[str, Any]]) -> None:
        openings = [row for row in stored if row["type"] == "PositionOpened"]
        if not openings:
            return
        db.execute(_DDL)
        for row in openings:
            db.execute(
                "INSERT INTO position_deposits"
                " (opened_seq, mint, deposit_lamports) VALUES (?, ?, ?);",
                (int(row["seq"]), mint, deposit_lamports),
            )

    return write


def _table_exists(db: sqlite3.Connection) -> bool:
    row = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?;", (_TABLE,)
    ).fetchone()
    return row is not None


def open_deposits(store: LedgerStore) -> dict[str, int]:
    """The deposit recorded for each mint's latest opening; empty when none was recorded."""
    db = store._db
    if not _table_exists(db):
        return {}
    rows = db.execute("SELECT mint, deposit_lamports FROM position_deposits ORDER BY opened_seq;")
    return {str(mint): int(lamports) for mint, lamports in rows.fetchall()}
