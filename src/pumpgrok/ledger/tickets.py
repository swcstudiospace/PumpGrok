"""SOL-YYYYMMDD-NNN ticket allocation over JournalNote rows (R29, R33).

Tickets are ``JournalNote`` rows with ``note_kind=ticket``; NNN is one plus
the highest NNN already stored for the day, so explicit tickets never collide with
automatic ones. Allocation goes through ``append_batch`` — the single
atomic path — with the deterministic ``ticket:<id>`` idempotency key, so two
concurrent allocators cannot take the same number: the loser sees a UNIQUE
violation, recounts, and takes the next number.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from pumpgrok.core.errors import PumpgrokError
from pumpgrok.ledger.store import LedgerStore

TICKET_RE = re.compile(r"^SOL-(\d{8})-(\d{3})$")
MAX_ATTEMPTS = 10


class TicketAllocationFailed(PumpgrokError):
    """Ticket allocation lost the idempotency race too many times."""

    code = "ticket_allocation_failed"


def day_ticket_count(store: LedgerStore, compact_day: str) -> int:
    """Count ticket rows whose payload carries a ticket id for the day."""
    row = store._db.execute(
        "SELECT COUNT(*) FROM events WHERE type = 'JournalNote' AND payload_json LIKE ?;",
        (f"%SOL-{compact_day}-%",),
    ).fetchone()
    return int(row[0])


def day_max_ticket_number(store: LedgerStore, compact_day: str) -> int:
    """Highest NNN among the day's stored ticket ids; 0 when the day has none."""
    prefix = f"SOL-{compact_day}-"
    rows = store._db.execute(
        "SELECT payload_json FROM events WHERE type = 'JournalNote' AND payload_json LIKE ?;",
        (f"%{prefix}%",),
    ).fetchall()
    highest = 0
    for (payload_json,) in rows:
        payload = json.loads(payload_json)
        if payload.get("note_kind") != "ticket":
            continue
        refs = payload.get("refs") or []
        ticket_id = str(refs[0]) if refs else ""
        if ticket_id.startswith(prefix) and TICKET_RE.fullmatch(ticket_id):
            highest = max(highest, int(ticket_id[len(prefix) :]))
    return highest


def allocate_ticket(
    store: LedgerStore,
    *,
    ts_utc: str,
    source: str,
    correlation_id: str,
    seat: str,
    title: str,
) -> str:
    """Allocate the next ``SOL-YYYYMMDD-NNN`` id for the UTC day and store it.

    Returns the ticket id; the stored JournalNote carries it in ``refs[0]``.
    """
    compact_day = ts_utc[:10].replace("-", "")
    for _ in range(MAX_ATTEMPTS):
        ticket_id = f"SOL-{compact_day}-{day_max_ticket_number(store, compact_day) + 1:03d}"
        row: dict[str, Any] = {
            "ts_utc": ts_utc,
            "source": source,
            "correlation_id": correlation_id,
            "idempotency_key": f"ticket:{ticket_id}",
            "type": "JournalNote",
            "payload": {
                "source": source,
                "seat": seat,
                "note_kind": "ticket",
                "text": f"{ticket_id} {title}",
                "refs": [ticket_id],
            },
        }
        try:
            store.append_batch([row])
        except sqlite3.IntegrityError:
            continue
        return ticket_id
    raise TicketAllocationFailed(f"could not allocate a ticket for {compact_day}")
