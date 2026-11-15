"""Ticket to strategy attribution, written in the ticket's own transaction (STR-03, T-15-03-01).

strategy_ticket_refs maps one ticket id to one strategy id. Its primary key on the ticket
enforces one strategy per ticket, and append_with_ticket_ref writes the ticket's event and
its ref in one transaction: a refused link leaves no event behind, so attribution and the
chain never disagree. event_id is the stored row's hash, the event's identity in the chain.
A ticket attributed to no strategy (the legacy path) has no row.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from pumpgrok.core.errors import PumpgrokError
from pumpgrok.ledger.store import LedgerStore

__all__ = ["TicketAttributionConflict", "append_with_ticket_ref", "event_id_for", "load_refs"]


class TicketAttributionConflict(PumpgrokError):
    """The ticket already belongs to a strategy; a second link is refused."""

    code = "ticket_attribution_conflict"


def load_refs(store: LedgerStore) -> dict[str, str]:
    """Every ticket id mapped to its strategy id."""
    rows = store._db.execute("SELECT ticket_id, strategy_id FROM strategy_ticket_refs;").fetchall()
    return {str(ticket): str(strategy) for ticket, strategy in rows}


def event_id_for(store: LedgerStore, ticket_id: str) -> str | None:
    """The event hash recorded with a ticket's ref, or None when the ticket has no ref."""
    row = store._db.execute(
        "SELECT event_id FROM strategy_ticket_refs WHERE ticket_id = ?;", (ticket_id,)
    ).fetchone()
    return None if row is None else str(row[0])


def append_with_ticket_ref(
    store: LedgerStore,
    row: Mapping[str, Any],
    *,
    ticket_id: str,
    strategy_id: str,
) -> dict[str, Any]:
    """Append the ticket's event and link it to a strategy, in one transaction.

    Raises TicketAttributionConflict, appending nothing, when the ticket already has a ref.
    """
    if not ticket_id or not strategy_id:
        raise ValueError("a ticket ref needs a ticket id and a strategy id")
    if ticket_id in load_refs(store):
        raise TicketAttributionConflict(f"ticket {ticket_id} is already attributed")

    def write_ref(db: sqlite3.Connection, stored: list[dict[str, Any]]) -> None:
        try:
            db.execute(
                "INSERT INTO strategy_ticket_refs (ticket_id, strategy_id, event_id)"
                " VALUES (?, ?, ?);",
                (ticket_id, strategy_id, str(stored[0]["hash"])),
            )
        except sqlite3.IntegrityError as exc:
            raise TicketAttributionConflict(f"ticket {ticket_id} is already attributed") from exc

    return store.append_batch([row], sidecar=write_ref)[0]
