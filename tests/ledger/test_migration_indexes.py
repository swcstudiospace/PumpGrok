"""M-2026-1120 (T1482-data): the ledger carries the three migration indexes.

A07 owns migrations/20261120_01_events_indexes.{up,down}.sql; A05 consumes
them verbatim in ``LedgerStore`` via ``_SCHEMA``. These tests prove fresh
ledgers, reopened ledgers and direct up.sql application agree on the index
set, and that the down file drops exactly those indexes (rows untouched).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.ledger.store import LedgerStore

_REPO = Path(__file__).resolve().parents[2]
_UP = _REPO / "src/pumpgrok/ledger/migrations/20261120_01_events_indexes.up.sql"
_DOWN = _REPO / "src/pumpgrok/ledger/migrations/20261120_01_events_indexes.down.sql"

EXPECTED = {
    "idx_events_type_ts": ["type", "ts_utc", "seq"],
    "idx_events_correlation": ["correlation_id", "seq"],
    "idx_events_ts_seq": ["ts_utc", "seq"],
}


def _event(**overrides):
    base = {
        "ts_utc": "2026-01-01T00:00:00.000001Z",
        "source": "paper",
        "correlation_id": "01J0000000000000000000000",
        "idempotency_key": "aaaabbbbccccdddd",
        "type": "JournalNote",
        "payload": {"source": "paper", "seat": "desk", "note_kind": "note", "text": "skip"},
    }
    base.update(overrides)
    return base


def _index_columns(db_path: Path) -> dict[str, list[str]]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name NOT LIKE 'sqlite_autoindex_%'"
        ).fetchall()
        return {
            name: [row[2] for row in conn.execute(f"PRAGMA index_info({name})").fetchall()]
            for (name,) in rows
        }
    finally:
        conn.close()


def test_fresh_ledger_has_exactly_the_migration_indexes(tmp_path) -> None:
    path = tmp_path / "ledger.sqlite"
    store = LedgerStore(path)
    store.append(**_event())
    store.close()
    assert _index_columns(path) == EXPECTED


def test_reopen_is_idempotent_and_keeps_rows(tmp_path) -> None:
    path = tmp_path / "ledger.sqlite"
    store = LedgerStore(path)
    store.append(**_event())
    store.close()
    reopened = LedgerStore(path)
    assert _index_columns(path) == EXPECTED
    assert reopened.count() == 1
    assert reopened.verify() is True
    reopened.close()


def test_up_and_down_sql_match_store_indexes(tmp_path) -> None:
    path = tmp_path / "ledger.sqlite"
    store = LedgerStore(path)
    store.append(**_event())
    store.close()
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_DOWN.read_text(encoding="utf-8"))
        assert _index_columns(path) == {}
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        conn.executescript(_UP.read_text(encoding="utf-8"))
        assert _index_columns(path) == EXPECTED
    finally:
        conn.close()
