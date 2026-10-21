"""Tracer RED: append one event and verify the chain (FOUND-013)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.ledger.store import LedgerStore


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


def test_first_append_yields_seq1_with_genesis_prev_hash(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    row = store.append(**_event())
    assert row["seq"] == 1
    assert row["prev_hash"] == "0" * 64
    assert store.verify() is True


def test_second_append_chains_prev_hash(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    first = store.append(**_event())
    second = store.append(
        **_event(ts_utc="2026-01-01T00:00:01.000001Z", idempotency_key="eeeffff00001111")
    )
    assert second["seq"] == 2
    assert second["prev_hash"] == first["hash"]
    assert store.verify() is True


def test_update_and_delete_raise(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    store.append(**_event())
    with pytest.raises(Exception):
        store._db.execute("UPDATE events SET type='X' WHERE seq=1")
    with pytest.raises(Exception):
        store._db.execute("DELETE FROM events WHERE seq=1")


def test_duplicate_idempotency_key_refused(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    store.append(**_event())
    with pytest.raises(Exception):
        store.append(**_event(ts_utc="2026-01-01T00:00:02.000001Z"))
    assert store.count() == 1


def test_snapshots_are_append_only(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    store.write_snapshot(seq=1, ts_utc="2026-01-01T00:00:00.000001Z", state={"a": 1})
    with pytest.raises(sqlite3.IntegrityError):
        store.write_snapshot(seq=1, ts_utc="2026-01-01T00:00:00.000002Z", state={"a": 2})
    with pytest.raises(sqlite3.IntegrityError):
        store._db.execute("UPDATE snapshots SET state_json='{}' WHERE seq=1")
    with pytest.raises(sqlite3.IntegrityError):
        store._db.execute("DELETE FROM snapshots WHERE seq=1")


def test_unknown_type_and_bad_payload_refused(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    with pytest.raises(ValueError):
        store.append(**_event(type="NotARealEvent", payload={"anything": "goes"}))
    with pytest.raises(ValueError):
        store.append(**_event(payload={"source": "paper", "text": "skip", "surprise": 1}))
    assert store.count() == 0
