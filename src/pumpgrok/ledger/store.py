"""Hash-chained SQLite ledger (paper-engine.md 3.2, R26/R28, FOUND-013).

Single writer: every append runs inside ``BEGIN IMMEDIATE``, reads the chain
head, computes ``(seq, prev_hash, hash)`` over canonical JSON, then commits.
The hash input is ``prev_hash, seq, ts_utc, source, correlation_id,
idempotency_key, type, payload_json`` (locked Q3: idempotency_key is NOT NULL
UNIQUE and must be covered by the chain). Genesis ``prev_hash`` is 64 zeros.
Replay ledgers are recreated each run via :func:`recreate_ledger_db` (remove
sqlite plus -wal/-shm before opening); they are never migrated.

Ids arrive via ``core/ids.py``; the store mints none.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pumpgrok.core.atomic_write import atomic_write_json
from pumpgrok.core.errors import PumpgrokError
from pumpgrok.core.idempotency import canonical_json

GENESIS_PREV_HASH = "0" * 64
SCHEMA_VERSION = "1"

SOURCES = frozenset({"paper", "replay", "manual"})

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA busy_timeout = 5000;
CREATE TABLE IF NOT EXISTS events (
  seq             INTEGER PRIMARY KEY,
  ts_utc          TEXT    NOT NULL,
  source          TEXT    NOT NULL,
  correlation_id  TEXT    NOT NULL,
  idempotency_key TEXT    NOT NULL UNIQUE,
  type            TEXT    NOT NULL,
  payload_json    TEXT    NOT NULL,
  prev_hash       TEXT    NOT NULL,
  hash            TEXT    NOT NULL UNIQUE
);
CREATE TRIGGER IF NOT EXISTS events_append_only_u BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_append_only_d BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TABLE IF NOT EXISTS snapshots (
  seq         INTEGER PRIMARY KEY,
  ts_utc      TEXT    NOT NULL,
  state_json  TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class LedgerInconsistent(PumpgrokError):
    """A row hash recomputation mismatched; the ledger must not be trusted."""

    code = "ledger_inconsistent"


def recreate_ledger_db(path: str | Path) -> Path:
    """Delete sqlite plus -wal/-shm sidecars so a replay run starts empty."""
    target = Path(path)
    for candidate in (target, Path(str(target) + "-wal"), Path(str(target) + "-shm")):
        candidate.unlink(missing_ok=True)
    return target


def _row_hash(
    *,
    prev_hash: str,
    seq: int,
    ts_utc: str,
    source: str,
    correlation_id: str,
    idempotency_key: str,
    type: str,
    payload_json: str,
) -> str:
    body = canonical_json(
        {
            "correlation_id": correlation_id,
            "idempotency_key": idempotency_key,
            "payload_json": payload_json,
            "prev_hash": prev_hash,
            "seq": seq,
            "source": source,
            "ts_utc": ts_utc,
            "type": type,
        }
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class LedgerStore:
    """Append-only hash-chained event ledger over sqlite3 stdlib."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.path), isolation_level=None)
        self._db.execute("PRAGMA journal_mode = WAL;")
        self._db.execute("PRAGMA synchronous = FULL;")
        self._db.execute("PRAGMA busy_timeout = 5000;")
        self._db.executescript(_SCHEMA)

    def append(
        self,
        *,
        ts_utc: str,
        source: str,
        correlation_id: str,
        idempotency_key: str,
        type: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Append one event; returns the stored row. Raises on duplicates."""
        if source not in SOURCES:
            raise ValueError(f"source must be one of {sorted(SOURCES)}, got {source!r}")
        if not correlation_id or not idempotency_key or not type or not ts_utc:
            raise ValueError("ts_utc, correlation_id, idempotency_key and type are required")
        payload_json = canonical_json(dict(payload))
        db = self._db
        db.execute("BEGIN IMMEDIATE;")
        try:
            head = db.execute("SELECT seq, hash FROM events ORDER BY seq DESC LIMIT 1;").fetchone()
            if head is None:
                seq, prev_hash = 1, GENESIS_PREV_HASH
            else:
                seq, prev_hash = head[0] + 1, head[1]
            hash_ = _row_hash(
                prev_hash=prev_hash,
                seq=seq,
                ts_utc=ts_utc,
                source=source,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                type=type,
                payload_json=payload_json,
            )
            db.execute(
                "INSERT INTO events (seq, ts_utc, source, correlation_id,"
                " idempotency_key, type, payload_json, prev_hash, hash)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (
                    seq,
                    ts_utc,
                    source,
                    correlation_id,
                    idempotency_key,
                    type,
                    payload_json,
                    prev_hash,
                    hash_,
                ),
            )
            db.execute("COMMIT;")
        except Exception:
            try:
                db.execute("ROLLBACK;")
            except sqlite3.Error:
                pass
            raise
        return {
            "seq": seq,
            "ts_utc": ts_utc,
            "source": source,
            "correlation_id": correlation_id,
            "idempotency_key": idempotency_key,
            "type": type,
            "payload_json": payload_json,
            "prev_hash": prev_hash,
            "hash": hash_,
        }

    def verify(self) -> bool:
        """Recompute every row hash in seq order; raise LedgerInconsistent on mismatch."""
        rows = self._db.execute(
            "SELECT seq, ts_utc, source, correlation_id, idempotency_key,"
            " type, payload_json, prev_hash, hash FROM events ORDER BY seq ASC;"
        ).fetchall()
        expected_prev = GENESIS_PREV_HASH
        for (
            seq,
            ts_utc,
            source,
            correlation_id,
            idempotency_key,
            type,
            payload_json,
            prev_hash,
            hash_,
        ) in rows:
            if prev_hash != expected_prev:
                raise LedgerInconsistent(
                    f"seq {seq}: prev_hash does not chain",
                    seq=seq,
                )
            recomputed = _row_hash(
                prev_hash=prev_hash,
                seq=seq,
                ts_utc=ts_utc,
                source=source,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                type=type,
                payload_json=payload_json,
            )
            if recomputed != hash_:
                raise LedgerInconsistent(f"seq {seq}: hash mismatch", seq=seq)
            expected_prev = hash_
        return True

    def count(self) -> int:
        """Number of events stored."""
        row = self._db.execute("SELECT COUNT(*) FROM events;").fetchone()
        return int(row[0])

    def write_snapshot(self, *, seq: int, ts_utc: str, state: Mapping[str, Any]) -> None:
        """Fold state at seq into the snapshots table (append-only like events)."""
        self._db.execute(
            "INSERT OR REPLACE INTO snapshots (seq, ts_utc, state_json) VALUES (?, ?, ?);",
            (seq, ts_utc, canonical_json(dict(state))),
        )

    def export_snapshot_file(self, path: str | Path, state: Mapping[str, Any]) -> None:
        """Write state to path via tmp+fsync+os.replace (loud on OSError)."""
        atomic_write_json(path, dict(state))

    def close(self) -> None:
        """Close the underlying connection."""
        self._db.close()
