<<<<<<< HEAD
"""STR-03: ticket attribution refs; legacy_screening writes none."""

from __future__ import annotations

from pathlib import Path

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.strategy_state import read_attribution_refs, record_attribution_ref


def _open_store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(str(tmp_path / "ledger.sqlite"))


def test_new_strategy_refs_round_trip(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        assert (
            record_attribution_ref(
                store,
                strategy_id="momentum_breakout",
                ticket_id="SOL-20260101-001",
                mint="MintA",
                ts_utc="2026-01-01T00:00:00Z",
                source="paper",
                correlation_id="ticket-ref-1",
            )
            == "SOL-20260101-001"
        )
        assert read_attribution_refs(store, "momentum_breakout") == [
            {"ticket_id": "SOL-20260101-001", "mint": "MintA"}
        ]
=======
"""STR-03 / T-15-03-01: one strategy per ticket, written with the ticket's own event.

strategy_ticket_refs is a sidecar table keyed by ticket id. A second strategy for the same
ticket raises and leaves the event unappended, so attribution and the chain never disagree.
The legacy strategy writes no ref row.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.ledger import ticket_refs
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.ticket_refs import TicketAttributionConflict
from pumpgrok.ledger.tickets import allocate_ticket

TICKET = "SOL-20260101-001"
CORR = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


def _ticket_row(ticket: str = TICKET) -> dict[str, Any]:
    return {
        "ts_utc": "2026-01-01T00:00:00Z",
        "source": "paper",
        "correlation_id": CORR,
        "idempotency_key": f"ticket:{ticket}",
        "type": "JournalNote",
        "payload": {
            "source": "paper",
            "seat": "bot-04-sniper",
            "note_kind": "ticket",
            "text": f"{ticket} test",
            "refs": [ticket],
        },
    }


def _count(path: Path, table: str) -> int:
    with sqlite3.connect(path) as db:
        return int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_linking_writes_one_ref_row_with_the_event(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    store = LedgerStore(str(path))
    try:
        ticket_refs.append_with_ticket_ref(
            store, _ticket_row(), ticket_id=TICKET, strategy_id="momentum_breakout"
        )
        refs = ticket_refs.load_refs(store)
        assert refs == {TICKET: "momentum_breakout"}
        assert store.count() == 1
        stored_hash = store.read(limit=None)[-1]["hash"]
        assert ticket_refs.event_id_for(store, TICKET) == stored_hash
    finally:
        store.close()
    assert _count(path, "strategy_ticket_refs") == 1


def test_second_strategy_for_the_same_ticket_raises_and_appends_nothing(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    store = LedgerStore(str(path))
    try:
        ticket_refs.append_with_ticket_ref(
            store, _ticket_row(), ticket_id=TICKET, strategy_id="momentum_breakout"
        )
        with pytest.raises(TicketAttributionConflict):
            ticket_refs.append_with_ticket_ref(
                store, _ticket_row(), ticket_id=TICKET, strategy_id="mean_reversion"
            )
        assert ticket_refs.load_refs(store) == {TICKET: "momentum_breakout"}
        assert store.count() == 1
    finally:
        store.close()
    assert _count(path, "strategy_ticket_refs") == 1


def test_same_strategy_twice_for_one_ticket_also_raises(tmp_path: Path) -> None:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        ticket_refs.append_with_ticket_ref(
            store, _ticket_row(), ticket_id=TICKET, strategy_id="momentum_breakout"
        )
        with pytest.raises(TicketAttributionConflict):
            ticket_refs.append_with_ticket_ref(
                store,
                {**_ticket_row(), "idempotency_key": "ticket:second"},
                ticket_id=TICKET,
                strategy_id="momentum_breakout",
            )
        assert store.count() == 1
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
    finally:
        store.close()


<<<<<<< HEAD
def test_legacy_writes_no_refs(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        assert (
            record_attribution_ref(
                store,
                strategy_id="legacy_screening",
                ticket_id="SOL-20260101-001",
                mint="MintA",
                ts_utc="2026-01-01T00:00:00Z",
                source="paper",
                correlation_id="ticket-ref-2",
            )
            is None
        )
        assert read_attribution_refs(store, "legacy_screening") == []
        assert read_attribution_refs(store, "momentum_breakout") == []
    finally:
        store.close()
=======
def test_legacy_ticket_writes_no_ref_row(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    store = LedgerStore(str(path))
    try:
        ticket = allocate_ticket(
            store,
            ts_utc="2026-01-01T00:00:00Z",
            source="paper",
            correlation_id=CORR,
            seat="bot-00-chief",
            title="legacy",
        )
        assert ticket == TICKET
        assert ticket_refs.load_refs(store) == {}
    finally:
        store.close()
    assert _count(path, "strategy_ticket_refs") == 0
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
