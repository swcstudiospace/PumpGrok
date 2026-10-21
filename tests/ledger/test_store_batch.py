"""Tracer: one JournalNote through append_batch into views/export with verify."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.ledger.reconcile import CONSISTENT, reconcile
from pumpgrok.ledger.store import LedgerStore


def _note(**overrides):
    base = {
        "ts_utc": "2026-01-01T00:00:00.000001Z",
        "source": "replay",
        "correlation_id": "01J0000000000000000000000",
        "idempotency_key": "aaaabbbbccccdddd",
        "type": "JournalNote",
        "payload": {"source": "replay", "seat": "desk", "note_kind": "note", "text": "skip"},
    }
    base.update(overrides)
    return base


def test_batch_single_journal_note_verifies(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    rows = store.append_batch([_note()])
    assert len(rows) == 1
    assert rows[0]["seq"] == 1
    assert rows[0]["prev_hash"] == "0" * 64
    assert store.verify() is True
    result = reconcile(store)
    assert result["status"] == CONSISTENT
    assert result["tail_events"] == 1
    assert result["head_seq"] == 1


def test_batch_duplicate_key_refused_no_partial_rows(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    with pytest.raises(sqlite3.IntegrityError):
        store.append_batch(
            [
                _note(),
                _note(ts_utc="2026-01-01T00:00:01.000001Z"),
            ]
        )
    assert store.count() == 0
    assert store.verify() is True


def test_batch_rejects_float_money(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    bad = _note()
    bad["payload"] = dict(bad["payload"])
    bad["payload"]["text"] = 1.5  # type: ignore[dict-item]
    with pytest.raises((TypeError, ValueError)):
        store.append_batch([bad])
    assert store.count() == 0
