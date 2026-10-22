"""Regression: automatic ticket allocation skips numbers already taken on the day.

Greptile round 3 finding 18 (src/pumpgrok/ledger/tickets.py): an explicit
``ticket create --ticket SOL-<day>-002`` on an empty ledger stores the ticket
under the same ``ticket:<id>`` key. The next automatic allocation derived its
number from the day's row count, chose 002 again, and failed on the duplicate
key ten times, so allocation stayed stuck for that day.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.tickets import TICKET_RE, allocate_ticket

DAY = "2026-01-01"
COMPACT = "20260101"


def _explicit_ticket(store: LedgerStore, ticket_id: str, seq_ts: str) -> None:
    """Store a ticket the same way ``ticket create --ticket`` does in cli.py."""
    store.append(
        ts_utc=seq_ts,
        source="paper",
        correlation_id="desk",
        idempotency_key=f"ticket:{ticket_id}",
        type="JournalNote",
        payload={
            "source": "paper",
            "seat": "desk",
            "note_kind": "ticket",
            "text": f"{ticket_id} lead",
            "refs": [ticket_id],
        },
    )


def _allocate(store: LedgerStore, ts: str) -> str:
    return allocate_ticket(
        store,
        ts_utc=ts,
        source="paper",
        correlation_id="desk",
        seat="desk",
        title="lead",
    )


def test_auto_allocation_skips_explicit_ticket_on_empty_ledger(tmp_path: Path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    _explicit_ticket(store, f"SOL-{COMPACT}-002", f"{DAY}T00:00:01.000001Z")
    ticket = _allocate(store, f"{DAY}T00:00:02.000001Z")
    assert ticket == f"SOL-{COMPACT}-003"
    assert TICKET_RE.fullmatch(ticket) is not None


def test_auto_allocation_after_explicit_gap_never_reuses_a_number(tmp_path: Path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    _explicit_ticket(store, f"SOL-{COMPACT}-001", f"{DAY}T00:00:01.000001Z")
    _explicit_ticket(store, f"SOL-{COMPACT}-005", f"{DAY}T00:00:02.000001Z")
    first = _allocate(store, f"{DAY}T00:00:03.000001Z")
    second = _allocate(store, f"{DAY}T00:00:04.000001Z")
    assert first == f"SOL-{COMPACT}-006"
    assert second == f"SOL-{COMPACT}-007"


def test_sequential_auto_allocations_stay_contiguous(tmp_path: Path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    issued = [_allocate(store, f"{DAY}T00:00:0{i}.000001Z") for i in range(1, 4)]
    assert issued == [f"SOL-{COMPACT}-001", f"SOL-{COMPACT}-002", f"SOL-{COMPACT}-003"]


def test_explicit_ticket_on_other_day_does_not_shift_today(tmp_path: Path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    _explicit_ticket(store, "SOL-20251231-009", "2025-12-31T23:59:59.000001Z")
    assert _allocate(store, f"{DAY}T00:00:01.000001Z") == f"SOL-{COMPACT}-001"


def test_stored_ticket_rows_keep_their_refs(tmp_path: Path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    ticket = _allocate(store, f"{DAY}T00:00:01.000001Z")
    rows: list[dict[str, Any]] = [
        e for e in store.read(types=["JournalNote"], limit=None) if e["payload"].get("refs")
    ]
    assert [row["payload"]["refs"] for row in rows] == [[ticket]]
