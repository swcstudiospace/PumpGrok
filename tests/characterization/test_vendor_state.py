"""Characterization: atomic state and corrupt quarantine (STRUCT-004).

Pins the ledger snapshot helper and the reputation book against
``vendor/grokbot-pumpfun/src/state.py:48-104`` (``StateStore`` atomic write,
corrupt quarantine) and ``vendor/grokbot-pumpfun/tests/test_state.py``
(vendor oracle, kept byte-identical per R53).

Adaptations from the oracle (deliberate):

- Atomic writes live in ``core/atomic_write.py`` (ordering is vendor-exact:
  tmp file in the same directory, ``json.dump``, ``flush``, ``os.fsync``,
  ``os.replace``, unlink tmp on failure) and are shared by the snapshot
  exporter (``LedgerStore.export_snapshot_file``) and the reputation book.
  One change from the vendor: ``OSError`` is never swallowed, the ledger
  must fail loudly.
- The vendor quarantines an unreadable state file to ``<name>.corrupt`` and
  starts clean. The reputation book (the desk's restart memory, R62) keeps
  that behavior with a timestamped suffix (``<name>.corrupt-<utc-stamp>``)
  so repeated crashes never overwrite the evidence, and marks the loaded
  book ``degraded`` so the paper engine refuses new entries until the book
  is restored or rebuilt from the ledger.
- ``RiskManager`` restore rows of the vendor file (positions, counters, and
  day rollover across a restart) are not repeated here: restart replay is
  pinned by ``ledger/reconcile.py`` (plan 04-01) and the check engine owns
  restore semantics in plan 04-05.
- All prose is English; the vendor text is Russian.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pumpgrok.core.atomic_write import atomic_write_json
from pumpgrok.engine.reputation import ReputationBook
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock

START = 1_800_000_000.0


@pytest.fixture
def clock() -> FixtureClock:
    return FixtureClock(start=START)


# --- atomic write ------------------------------------------------------------


def test_atomic_write_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "state" / "snapshot.json"
    atomic_write_json(target, {"day": "2026-08-26", "trades_today": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "day": "2026-08-26",
        "trades_today": 2,
    }


def test_atomic_write_creates_parent_directory(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "inside" / "state.json"
    atomic_write_json(target, {"day": "2026-08-26"})
    assert target.exists()


def test_atomic_write_leaves_no_temp_files(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    atomic_write_json(target, {"day": "2026-08-26"})
    leftovers = [p for p in tmp_path.iterdir() if p != target]
    assert leftovers == []


def test_atomic_write_is_loud_on_failure(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("in the way", encoding="utf-8")
    with pytest.raises(OSError):
        atomic_write_json(blocker / "state.json", {"a": 1})
    assert not (tmp_path / "blocker.state.json.tmp").exists()


def test_snapshot_export_writes_state_file(tmp_path: Path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    path = tmp_path / "snapshots" / "state.json"
    store.write_snapshot(seq=1, ts_utc="2026-01-01T00:00:01.000001Z", state={"cash": 1})
    store.export_snapshot_file(path, {"seq": 1, "cash": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"seq": 1, "cash": 1}
    assert [p for p in path.parent.iterdir() if p != path] == []


# --- reputation book: restart memory ----------------------------------------


def test_missing_file_starts_empty(tmp_path: Path, clock: FixtureClock) -> None:
    book = ReputationBook.load(tmp_path / "creators.json", clock=clock)
    assert book.creators == {}
    assert not book.degraded


def test_save_and_load_roundtrip(tmp_path: Path, clock: FixtureClock) -> None:
    path = tmp_path / "creators.json"
    book = ReputationBook.load(path, clock=clock)
    book.observe("CreatorA")
    book.save(path)
    reloaded = ReputationBook.load(path, clock=clock)
    assert set(reloaded.creators) == {"CreatorA"}
    assert not reloaded.degraded


def test_save_leaves_no_temp_files(tmp_path: Path, clock: FixtureClock) -> None:
    path = tmp_path / "creators.json"
    book = ReputationBook.load(path, clock=clock)
    book.save(path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["creators.json"]


def test_corrupt_file_is_quarantined_not_crashed(tmp_path: Path, clock: FixtureClock) -> None:
    path = tmp_path / "creators.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")
    book = ReputationBook.load(path, clock=clock)
    assert book.creators == {}
    assert book.degraded
    assert list(tmp_path.glob("creators.json.corrupt-*")) != []


def test_wrong_shape_is_quarantined_like_corruption(tmp_path: Path, clock: FixtureClock) -> None:
    path = tmp_path / "creators.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"creators": "not-a-dict"}), encoding="utf-8")
    book = ReputationBook.load(path, clock=clock)
    assert book.creators == {}
    assert book.degraded
    assert list(tmp_path.glob("creators.json.corrupt-*")) != []


def test_quarantine_keeps_book_usable(tmp_path: Path, clock: FixtureClock) -> None:
    """After quarantine the desk restarts on an empty book, never on a crash."""
    path = tmp_path / "creators.json"
    path.write_text("{broken", encoding="utf-8")
    book = ReputationBook.load(path, clock=clock)
    book.observe("FreshCreator")
    assert set(book.creators) == {"FreshCreator"}


def test_summary_is_readable() -> None:
    book = ReputationBook()
    book.observe("CreatorA")
    text = book.summary()
    assert "1 creators" in text
    assert "rugs" in text
