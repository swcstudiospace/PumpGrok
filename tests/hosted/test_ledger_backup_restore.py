"""HOST-07: backup round-trips; restore verifies then replaces."""

from __future__ import annotations

from pathlib import Path

from pumpgrok.ledger.backup import backup_ledger, restore_ledger, verify_candidate
from pumpgrok.ledger.store import LedgerStore


def _make_ledger(path: Path, n: int = 2) -> None:
    store = LedgerStore(path)
    try:
        for i in range(n):
            store.append(
                ts_utc="2026-01-01T00:00:00Z",
                source="paper",
                correlation_id=f"cid-{i}",
                idempotency_key=f"idem-{i}",
                type="JournalNote",
                payload={"source": "paper", "seat": "desk", "note_kind": "note", "text": f"n{i}"},
            )
    finally:
        store._db.close()


def test_backup_round_trips(tmp_path: Path) -> None:
    active = tmp_path / "ledger.sqlite"
    _make_ledger(active)
    state_dir = tmp_path / "state"
    dest = backup_ledger(active, state_dir)
    assert dest.is_file()
    assert verify_candidate(dest) is True


def test_restore_valid_candidate(tmp_path: Path) -> None:
    active = tmp_path / "ledger.sqlite"
    _make_ledger(active, n=2)
    state_dir = tmp_path / "state"
    dest = backup_ledger(active, state_dir)
    # Append one more row to active, then restore the backup over it.
    store = LedgerStore(active)
    try:
        store.append(
            ts_utc="2026-01-01T00:01:00Z",
            source="paper",
            correlation_id="cid-x",
            idempotency_key="idem-x",
            type="JournalNote",
            payload={"source": "paper", "seat": "desk", "note_kind": "note", "text": "x"},
        )
    finally:
        store._db.close()
    assert restore_ledger(dest, active) is True
    assert verify_candidate(active) is True


def test_corrupt_candidate_refused_byte_identical(tmp_path: Path) -> None:
    active = tmp_path / "ledger.sqlite"
    _make_ledger(active, n=1)
    state_dir = tmp_path / "state"
    dest = backup_ledger(active, state_dir)
    raw = dest.read_bytes()
    dest.write_bytes(raw[: len(raw) // 2])
    before = active.read_bytes()
    assert restore_ledger(dest, active) is False
    after = active.read_bytes()
    assert before == after
