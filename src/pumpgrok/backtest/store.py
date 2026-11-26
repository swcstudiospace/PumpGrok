<<<<<<< HEAD
"""Deterministic persisted backtest run records (BT-13).

Records persist sorted by idempotence key as byte-stable JSON lines, so
two runs over the same inputs produce byte-equal store files. No
timestamps, no randomness: the same record always serializes identically.
=======
"""Sidecar store for autonomous backtest results (BT-13).

One SQLite table under ``var/``, keyed by dataset digest, strategy version id,
params hash and grader version. Values are canonical JSON. A repeated key
returns the first row and writes nothing.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

import json
<<<<<<< HEAD
from pathlib import Path
from typing import Any

__all__ = ["RunStore", "dumps_record", "idempotence_key"]


def idempotence_key(dataset_digest: str, strategy_id: str, param_hash: str) -> str:
    """One run per (dataset digest, strategy id, param hash) triple."""
    return f"{dataset_digest}:{strategy_id}:{param_hash}"


def dumps_record(record: dict[str, Any]) -> bytes:
    """Byte-stable serialization of one record (sorted keys, newline terminated)."""
    return (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class RunStore:
    """Append/read store of backtest run records under a state path."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        """The backing file path."""
        return self._path

    def has(self, key: str) -> bool:
        """Whether a record with this idempotence key already persisted."""
        return any(record.get("idempotence_key") == key for record in self.load_all())

    def save(self, record: dict[str, Any]) -> dict[str, Any]:
        """Persist one record; returns the stored record unchanged."""
        with self._path.open("ab") as handle:
            handle.write(dumps_record(record))
        return record

    def load_all(self) -> list[dict[str, Any]]:
        """All persisted records in idempotence-key order (deterministic)."""
        if not self._path.is_file():
            return []
        records = [
            json.loads(line)
            for line in self._path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        records.sort(key=lambda record: str(record.get("idempotence_key", "")))
        return records

    def get(self, key: str) -> dict[str, Any] | None:
        """One record by idempotence key, or None when absent."""
        for record in self.load_all():
            if record.get("idempotence_key") == key:
                return record
        return None
=======
import sqlite3
from pathlib import Path
from typing import Any

from pumpgrok.core.idempotency import canonical_json

__all__ = ["DEFAULT_STORE_PATH", "ResultStore", "edge_key"]

#: Gitignored sidecar. Callers may pass another path in tests.
DEFAULT_STORE_PATH = Path("var/backtest/results.sqlite")

_KEY_FIELDS = (
    "dataset_digest",
    "strategy_version_id",
    "params_hash",
    "grader_version",
)


def edge_key(
    dataset_digest: str,
    strategy_version_id: str,
    params_hash: str,
    grader_version: str,
) -> tuple[str, str, str, str]:
    """The four identity fields, in table order. Empty fields are refused."""
    key = (dataset_digest, strategy_version_id, params_hash, grader_version)
    for name, value in zip(_KEY_FIELDS, key, strict=True):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} must be a non-empty string")
    return key


class ResultStore:
    """Insert-or-get over the edge key. The file lives under ``var/`` by default."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_STORE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS results ("
                " dataset_digest TEXT NOT NULL,"
                " strategy_version_id TEXT NOT NULL,"
                " params_hash TEXT NOT NULL,"
                " grader_version TEXT NOT NULL,"
                " body TEXT NOT NULL,"
                " PRIMARY KEY (dataset_digest, strategy_version_id,"
                " params_hash, grader_version)"
                ")"
            )

    def get(self, key: tuple[str, str, str, str]) -> dict[str, Any] | None:
        """Return the stored mapping, or None. Opens a read-only connection."""
        raw = self.row_bytes(key)
        if raw is None:
            return None
        loaded = json.loads(raw)
        if not isinstance(loaded, dict):
            raise ValueError("stored body is not an object")
        return loaded

    def row_bytes(self, key: tuple[str, str, str, str]) -> str | None:
        """The canonical JSON text of one row, or None. Read-only."""
        checked = edge_key(*key)
        uri = self.path.resolve().as_uri() + "?mode=ro"
        db = sqlite3.connect(uri, uri=True)
        try:
            row = db.execute(
                "SELECT body FROM results WHERE dataset_digest = ?"
                " AND strategy_version_id = ? AND params_hash = ?"
                " AND grader_version = ?",
                checked,
            ).fetchone()
        finally:
            db.close()
        if row is None:
            return None
        return str(row[0])

    def insert_or_get(self, key: tuple[str, str, str, str], value: dict[str, Any]) -> str:
        """Insert canonical JSON, or return the existing row. Never updates."""
        checked = edge_key(*key)
        body = canonical_json(value)
        with self._connect() as db:
            db.execute(
                "INSERT INTO results (dataset_digest, strategy_version_id,"
                " params_hash, grader_version, body) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT DO NOTHING",
                (*checked, body),
            )
            row = db.execute(
                "SELECT body FROM results WHERE dataset_digest = ?"
                " AND strategy_version_id = ? AND params_hash = ?"
                " AND grader_version = ?",
                checked,
            ).fetchone()
        if row is None:  # pragma: no cover - the insert just ensured a row
            raise RuntimeError("edge row missing after insert-or-get")
        return str(row[0])

    def rows_for(self, strategy_version_id: str, params_hash: str) -> tuple[dict[str, Any], ...]:
        """Every row for a strategy version and params hash, in key order. Read-only."""
        if not strategy_version_id or not params_hash:
            raise ValueError("strategy_version_id and params_hash are required")
        uri = self.path.resolve().as_uri() + "?mode=ro"
        db = sqlite3.connect(uri, uri=True)
        try:
            found = db.execute(
                "SELECT body FROM results WHERE strategy_version_id = ?"
                " AND params_hash = ? ORDER BY dataset_digest, grader_version",
                (strategy_version_id, params_hash),
            ).fetchall()
        finally:
            db.close()
        rows: list[dict[str, Any]] = []
        for (raw,) in found:
            loaded = json.loads(str(raw))
            if not isinstance(loaded, dict):
                raise ValueError("stored body is not an object")
            rows.append(loaded)
        return tuple(rows)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.execute("PRAGMA journal_mode=DELETE")
        return db
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
