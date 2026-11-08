"""Sidecar sqlite for dedup, pending, and DLQ. Not the paper ledger."""

from __future__ import annotations

import contextlib
import json
import sqlite3
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


class EventStore:
    """Opens only the caller path. Refuses the paper ledger before connect."""

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

    def remember(self, event_id: str, priority: int, now: float) -> None:
        ttl = _TTL[priority]
        self._db.execute(
            "INSERT OR REPLACE INTO dedup (event_id, priority, expires_at) VALUES (?, ?, ?);",
            (event_id, priority, now + ttl),
        )

    def write_dlq(self, event: Event, *, reason: str) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO dlq (event_id, reason, body) VALUES (?, ?, ?);",
            (event.event_id, reason, _dump(event)),
        )

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
        db = self._db
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute(
                "SELECT body FROM dlq WHERE event_id = ?;",
                (event_id,),
            ).fetchone()
            if row is None:
                db.execute("ROLLBACK")
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
            db.execute("COMMIT")
        except Exception:
            with contextlib.suppress(sqlite3.Error):
                db.execute("ROLLBACK")
            raise
        return _load(body)

    def replace_pending(self, events: list[Event]) -> None:
        """Upsert queued events by id. Do not delete rows parked by dlq replay."""
        db = self._db
        db.execute("BEGIN IMMEDIATE")
        try:
            for event in events:
                body = _dump(event)
                existing = db.execute(
                    "SELECT seq FROM pending WHERE event_id = ?;",
                    (event.event_id,),
                ).fetchone()
                if existing is None:
                    seq_row = db.execute(
                        "SELECT COALESCE(MAX(seq), 0) + 1 FROM pending;"
                    ).fetchone()
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
            db.execute("COMMIT")
        except Exception:
            with contextlib.suppress(sqlite3.Error):
                db.execute("ROLLBACK")
            raise

    def load_pending(self) -> list[Event]:
        rows = self._db.execute("SELECT body FROM pending ORDER BY seq;").fetchall()
        return [_load(str(row[0])) for row in rows]

    def delete_pending(self, event_id: str) -> None:
        self._db.execute("DELETE FROM pending WHERE event_id = ?;", (event_id,))

    def mark_applied(self, event_id: str, applied_at: float) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO applied (event_id, applied_at) VALUES (?, ?);",
            (event_id, applied_at),
        )

    def is_applied(self, event_id: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM applied WHERE event_id = ?;",
            (event_id,),
        ).fetchone()
        return row is not None


def _dump(event: Event) -> str:
    return json.dumps(event.model_dump(mode="json"), sort_keys=True)


def _load(body: str) -> Event:
    data: dict[str, Any] = json.loads(body)
    data.pop("event_id", None)
    return Event.model_validate(data)
