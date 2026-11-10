"""Sidecar sqlite for dedup, pending, applied, and DLQ rows. Not the paper ledger.

Each mutating method is either one statement or one transaction. A crash leaves the
state from before the call or the state after it, never a mix.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pumpgrok.events.constants import P0_DEDUP_TTL_S, P1_DEDUP_TTL_S
from pumpgrok.events.errors import SidecarRefusal
from pumpgrok.events.models import Event
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending (
  seq INTEGER PRIMARY KEY,
  event_id TEXT NOT NULL,
  body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applied (
  event_id TEXT PRIMARY KEY,
  applied_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS dedup (
  event_id TEXT PRIMARY KEY,
  priority INTEGER NOT NULL,
  expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS dlq (
  event_id TEXT PRIMARY KEY,
  reason TEXT NOT NULL,
  body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cursors (
  name TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

_TTL = {0: P0_DEDUP_TTL_S, 1: P1_DEDUP_TTL_S}
_OVERFLOW = "overflow"


class EventStore:
    """Opens only the caller path. Refuses the paper ledger before connect.

    Transaction boundaries:
    - accept_queued: dedup row + pending row (P0/P1 accepted into a lane).
    - accept_overflow: dedup row + DLQ row (P0/P1 rejected by a full lane).
    - complete_applied: applied row + pending delete (P0/P1 handler succeeded).
    - fail_to_dlq: DLQ row + pending delete (any priority, handler failed terminally).
    - replace_pending: pending upserts for the given events (shutdown, P2 only).
    - delete_pending: one statement (P2 handler succeeded).
    """

    def __init__(self, path: str | Path) -> None:
        candidate = Path(path)
        if candidate.expanduser().resolve() == PAPER_LEDGER_PATH.expanduser().resolve():
            raise SidecarRefusal(path_name=f"PAPER_LEDGER_PATH {PAPER_LEDGER_PATH}")
        candidate.parent.mkdir(parents=True, exist_ok=True)
        self.path = candidate
        self._db = sqlite3.connect(str(candidate), isolation_level=None)
        self._db.execute("PRAGMA journal_mode = WAL;")
        self._db.execute("PRAGMA synchronous = FULL;")
        self._db.execute("PRAGMA busy_timeout = 5000;")
        self._db.executescript(_SCHEMA)
        self._db.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('schema', '1');")

    def close(self) -> None:
        self._db.close()

    def is_duplicate(self, event_id: str, now: float) -> bool:
        row = self._db.execute(
            "SELECT expires_at FROM dedup WHERE event_id = ?;",
            (event_id,),
        ).fetchone()
        if row is None:
            return False
        return float(row[0]) > now

    def accept_queued(self, event: Event, *, priority: int, now: float) -> None:
        """One transaction: dedup row and pending row. A raise leaves neither."""
        with self._transaction() as db:
            _remember(db, event.event_id, priority, now)
            _upsert_pending(db, event)

    def accept_overflow(self, event: Event, *, priority: int, now: float) -> None:
        """One transaction: dedup row and DLQ row with reason overflow."""
        with self._transaction() as db:
            _remember(db, event.event_id, priority, now)
            _insert_dlq(db, event, reason=_OVERFLOW)

    def complete_applied(self, event_id: str, applied_at: float) -> None:
        """One transaction: applied row and pending delete."""
        with self._transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO applied (event_id, applied_at) VALUES (?, ?);",
                (event_id, applied_at),
            )
            db.execute("DELETE FROM pending WHERE event_id = ?;", (event_id,))

    def fail_to_dlq(self, event: Event, *, reason: str) -> None:
        """One transaction: DLQ row and pending delete."""
        with self._transaction() as db:
            _insert_dlq(db, event, reason=reason)
            db.execute("DELETE FROM pending WHERE event_id = ?;", (event.event_id,))

    def write_dlq(self, event: Event, *, reason: str) -> None:
        """Single-statement DLQ write that leaves pending alone. Seeds rows for tests and tools."""
        _insert_dlq(self._db, event, reason=reason)

    def list_dlq(self) -> list[dict[str, str]]:
        rows = self._db.execute("SELECT event_id, reason FROM dlq ORDER BY event_id;").fetchall()
        return [{"event_id": str(row[0]), "reason": str(row[1])} for row in rows]

    def take_dlq(self, event_id: str) -> Event | None:
        row = self._db.execute(
            "SELECT body FROM dlq WHERE event_id = ?;",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        self._db.execute("DELETE FROM dlq WHERE event_id = ?;", (event_id,))
        return _load(str(row[0]))

    def purge_dlq(self, event_id: str) -> bool:
        cursor = self._db.execute("DELETE FROM dlq WHERE event_id = ?;", (event_id,))
        return cursor.rowcount > 0

    def move_dlq_to_pending(self, event_id: str) -> Event | None:
        """Move one DLQ row into pending. Delete only if that insert commits."""
        with self._transaction() as db:
            row = db.execute(
                "SELECT body FROM dlq WHERE event_id = ?;",
                (event_id,),
            ).fetchone()
            if row is None:
                return None
            body = str(row[0])
            seq_row = db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM pending;").fetchone()
            seq = int(seq_row[0]) if seq_row is not None else 1
            db.execute(
                "INSERT INTO pending (seq, event_id, body) VALUES (?, ?, ?);",
                (seq, event_id, body),
            )
            deleted = db.execute("DELETE FROM dlq WHERE event_id = ?;", (event_id,))
            if deleted.rowcount != 1:
                raise sqlite3.OperationalError("dlq row missing before commit")
        return _load(body)

    def replace_pending(self, events: list[Event]) -> None:
        """One transaction: upsert pending rows by id. Rows parked by DLQ replay stay."""
        with self._transaction() as db:
            for event in events:
                _upsert_pending(db, event)

    def load_pending(self) -> list[Event]:
        rows = self._db.execute("SELECT body FROM pending ORDER BY seq;").fetchall()
        return [_load(str(row[0])) for row in rows]

    def delete_pending(self, event_id: str) -> None:
        self._db.execute("DELETE FROM pending WHERE event_id = ?;", (event_id,))

    def is_applied(self, event_id: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM applied WHERE event_id = ?;",
            (event_id,),
        ).fetchone()
        return row is not None

    @contextlib.contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        db = self._db
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            db.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                db.execute("ROLLBACK")
            raise


def _remember(db: sqlite3.Connection, event_id: str, priority: int, now: float) -> None:
    db.execute(
        "INSERT OR REPLACE INTO dedup (event_id, priority, expires_at) VALUES (?, ?, ?);",
        (event_id, priority, now + _TTL[priority]),
    )


def _insert_dlq(db: sqlite3.Connection, event: Event, *, reason: str) -> None:
    db.execute(
        "INSERT OR REPLACE INTO dlq (event_id, reason, body) VALUES (?, ?, ?);",
        (event.event_id, reason, _dump(event)),
    )


def _upsert_pending(db: sqlite3.Connection, event: Event) -> None:
    body = _dump(event)
    existing = db.execute(
        "SELECT seq FROM pending WHERE event_id = ?;",
        (event.event_id,),
    ).fetchone()
    if existing is None:
        seq_row = db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM pending;").fetchone()
        seq = int(seq_row[0]) if seq_row is not None else 1
        db.execute(
            "INSERT INTO pending (seq, event_id, body) VALUES (?, ?, ?);",
            (seq, event.event_id, body),
        )
    else:
        db.execute(
            "UPDATE pending SET body = ? WHERE event_id = ?;",
            (body, event.event_id),
        )


def _dump(event: Event) -> str:
    return json.dumps(event.model_dump(mode="json"), sort_keys=True)


def _load(body: str) -> Event:
    data: dict[str, Any] = json.loads(body)
    data.pop("event_id", None)
    return Event.model_validate(data)
