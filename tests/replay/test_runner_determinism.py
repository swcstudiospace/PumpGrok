"""Deterministic replay tracer (paper-engine.md 4.4-4.5, PAPER-004).

Two seeded runs over the same fixture must produce identical hashes,
identical ledgers and a CONSISTENT chain: the clock, RNG and ULIDs all derive
from fixture stamps plus seed, never from host time.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pumpgrok.config.settings import FilterSettings
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.runner import ledger_events_hash, run_replay

SMOKE = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke"


def _rows(ledger: Path) -> list[tuple[object, ...]]:
    conn = sqlite3.connect(str(ledger))
    try:
        return [
            tuple(row)
            for row in conn.execute(
                "SELECT seq, ts_utc, source, correlation_id,"
                " idempotency_key, type, payload_json, prev_hash, hash"
                " FROM events ORDER BY seq ASC;"
            ).fetchall()
        ]
    finally:
        conn.close()


def test_two_seeded_runs_produce_identical_hashes(tmp_path: Path) -> None:
    first = run_replay(SMOKE, FilterSettings(), ledger_path=tmp_path / "a.sqlite")
    second = run_replay(SMOKE, FilterSettings(), ledger_path=tmp_path / "b.sqlite")

    assert first.events_hash == second.events_hash
    assert first.events_hash == ledger_events_hash(tmp_path / "a.sqlite")
    assert _rows(tmp_path / "a.sqlite") == _rows(tmp_path / "b.sqlite")


def test_replay_ledger_verifies_consistent_and_holds_one_verdict(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    result = run_replay(SMOKE, FilterSettings(), ledger_path=ledger)

    store = LedgerStore(ledger)
    try:
        assert store.verify() is True
    finally:
        store.close()
    (row,) = _rows(ledger)
    assert row[2] == "replay"
    assert row[5] == "JournalNote"
    assert result.events_read == 4
    assert result.seq == 1
