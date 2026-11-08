"""EventStore transactions: a failed write leaves the rows from before the call."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from pumpgrok.events.models import Event, EventKind
from pumpgrok.events.store import EventStore


def _trade(occurred_at: str) -> Event:
    return Event(
        kind=EventKind.trade,
        entity_id="mint",
        payload={"n": occurred_at},
        occurred_at=occurred_at,
    )


def _rename(path: Path, old: str, new: str) -> None:
    with closing(sqlite3.connect(path, isolation_level=None)) as db:
        db.execute(f"ALTER TABLE {old} RENAME TO {new}")


def _count(path: Path, table: str) -> int:
    with closing(sqlite3.connect(path)) as db:
        row = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    assert row is not None
    return int(row[0])


def test_complete_applied_keeps_pending_row_when_applied_write_fails(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    store = EventStore(sidecar)
    event = _trade("t1")
    store.accept_queued(event, priority=1, now=0.0)

    _rename(sidecar, "applied", "applied_hidden")
    with pytest.raises(sqlite3.OperationalError):
        store.complete_applied(event.event_id, 1.0)
    _rename(sidecar, "applied_hidden", "applied")

    assert [item.event_id for item in store.load_pending()] == [event.event_id]
    assert store.is_applied(event.event_id) is False
    store.close()


def test_fail_to_dlq_keeps_pending_row_when_dlq_write_fails(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    store = EventStore(sidecar)
    event = _trade("t1")
    store.accept_queued(event, priority=1, now=0.0)

    _rename(sidecar, "dlq", "dlq_hidden")
    with pytest.raises(sqlite3.OperationalError):
        store.fail_to_dlq(event, reason="poison")
    _rename(sidecar, "dlq_hidden", "dlq")

    assert [item.event_id for item in store.load_pending()] == [event.event_id]
    assert store.list_dlq() == []
    store.close()


def test_accept_overflow_writes_dedup_and_dlq_rows_only(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    store = EventStore(sidecar)
    event = _trade("t1")
    store.accept_overflow(event, priority=1, now=0.0)

    assert store.is_duplicate(event.event_id, 1.0) is True
    assert store.list_dlq() == [{"event_id": event.event_id, "reason": "overflow"}]
    assert store.load_pending() == []
    store.close()


def test_replace_pending_upserts_by_event_id(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    store = EventStore(sidecar)
    first = _trade("t1")
    second = _trade("t2")
    store.replace_pending([first, second])
    store.replace_pending([first])
    store.replace_pending([second])

    assert [item.event_id for item in store.load_pending()] == [first.event_id, second.event_id]
    assert _count(sidecar, "pending") == 2
    store.close()
