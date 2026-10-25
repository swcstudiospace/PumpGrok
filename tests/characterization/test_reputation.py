"""Characterization: creator reputation memory (STRUCT-003).

Pins ``engine/reputation.py`` against
``vendor/grokbot-pumpfun/tests/test_reputation.py`` (vendor oracle, kept
byte-identical per R53).

Divergences from the oracle (deliberate):

- The book carries the injected clock: ``load(path, clock)``,
  ``forget_older_than(days, now)`` with a required ``now``, and
  ``last_seen``/``updated_at`` stamped from the clock. Tests use
  ``FixtureClock`` with explicit timestamps.
- ``verdict`` and ``summary`` are English ASCII (``creator_rugged ...``).
- Persistence goes through ``core/atomic_write.py`` keeping the vendor
  JSON shape; an ``OSError`` propagates instead of being swallowed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import pumpgrok.engine.reputation as reputation_module
from pumpgrok.engine.reputation import MAX_CREATORS, CreatorRecord, ReputationBook
from pumpgrok.replay.clock import FixtureClock

NOW = 1_700_000_000.0


@pytest.fixture
def book() -> ReputationBook:
    book = ReputationBook()
    book._clock = FixtureClock()
    return book


def rug(book: ReputationBook, creator: str = "C1", pct: float = -85.0) -> None:
    book.record_close(creator, pnl_lamports=-400_000_000, return_pct=pct, rug_loss_pct=60.0)


# --- accounting -------------------------------------------------------------


def test_unknown_creator_is_not_blocked(book: ReputationBook) -> None:
    assert book.verdict("new", block_after_rugs=1) is None
    assert book.verdict(None, block_after_rugs=1) is None


def test_rug_blocks_next_token(book: ReputationBook) -> None:
    rug(book)
    assert book.creators["C1"].rugs == 1
    verdict = book.verdict("C1", block_after_rugs=1)
    assert verdict is not None and "creator_rugged" in verdict


def test_moderate_loss_is_not_a_rug(book: ReputationBook) -> None:
    book.record_close("C1", pnl_lamports=-100_000_000, return_pct=-35.0, rug_loss_pct=60.0)
    assert book.creators["C1"].rugs == 0
    assert book.verdict("C1", block_after_rugs=1) is None


def test_rug_threshold_boundary(book: ReputationBook) -> None:
    book.record_close("C1", pnl_lamports=-300_000_000, return_pct=-60.0, rug_loss_pct=60.0)
    assert book.creators["C1"].rugs == 1
    book.record_close("C2", pnl_lamports=-300_000_000, return_pct=-59.9, rug_loss_pct=60.0)
    assert book.creators["C2"].rugs == 0


def test_tolerance_configurable(book: ReputationBook) -> None:
    rug(book)
    assert book.verdict("C1", block_after_rugs=2) is None
    rug(book)
    assert book.verdict("C1", block_after_rugs=2) is not None


def test_zero_disables_blocking(book: ReputationBook) -> None:
    rug(book)
    assert book.verdict("C1", block_after_rugs=0) is None


def test_profit_does_not_erase_history(book: ReputationBook) -> None:
    """One good exit does not cancel an address that already rugged."""
    rug(book)
    book.record_close("C1", pnl_lamports=1_000_000_000, return_pct=50.0, rug_loss_pct=60.0)
    assert book.verdict("C1", block_after_rugs=1) is not None
    assert book.creators["C1"].realized_pnl_lamports == 600_000_000


def test_counters_accumulate(book: ReputationBook) -> None:
    book.observe("C1")
    book.record_open("C1")
    book.record_close("C1", pnl_lamports=0, return_pct=0.0, rug_loss_pct=60.0)
    record = book.creators["C1"]
    assert (record.tokens_seen, record.tokens_bought, record.closed) == (1, 1, 1)
    assert record.worst_loss_pct == 0.0  # no losses seen


def test_worst_result_is_remembered(book: ReputationBook) -> None:
    book.record_close("C1", pnl_lamports=-100_000_000, return_pct=-20.0, rug_loss_pct=60.0)
    book.record_close("C1", pnl_lamports=-400_000_000, return_pct=-90.0, rug_loss_pct=60.0)
    assert book.creators["C1"].worst_loss_pct == -90.0


# --- disk --------------------------------------------------------------------


def test_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "creators.json"
    clock = FixtureClock()
    fresh = ReputationBook()
    fresh._clock = clock
    rug(fresh)
    fresh.save(path)
    reloaded = ReputationBook.load(path)
    assert reloaded.verdict("C1", block_after_rugs=1) is not None
    assert reloaded.updated_at == clock.now()


def test_save_keeps_vendor_json_shape(tmp_path: Path) -> None:
    path = tmp_path / "creators.json"
    fresh = ReputationBook()
    rug(fresh)
    fresh.save(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert set(raw) == {"version", "creators", "updated_at"}
    assert raw["creators"]["C1"]["rugs"] == 1


def test_missing_file_is_empty_book(tmp_path: Path) -> None:
    assert ReputationBook.load(tmp_path / "no.json").creators == {}


def test_corrupt_file_does_not_crash(tmp_path: Path) -> None:
    path = tmp_path / "creators.json"
    path.write_text("{not json")
    assert ReputationBook.load(path).creators == {}


def test_save_leaves_no_temp_files(tmp_path: Path) -> None:
    path = tmp_path / "creators.json"
    b = ReputationBook()
    rug(b)
    b.save(path)
    assert [p.name for p in tmp_path.iterdir() if ".tmp" in p.name] == []


def test_save_stamps_clock_time(tmp_path: Path) -> None:
    clock = FixtureClock()
    b = ReputationBook()
    b._clock = clock
    path = tmp_path / "creators.json"
    b.save(path)
    assert b.updated_at == clock.now()


# --- maintenance ---------------------------------------------------------------


def test_forgets_stale_but_keeps_rugs(book: ReputationBook) -> None:
    book.observe("clean")
    rug(book, "bad")
    forgotten = book.forget_older_than(30.0, NOW + 60 * 86_400)
    assert forgotten == 1
    assert "clean" not in book.creators
    assert "bad" in book.creators  # rugs are never forgotten


def test_forget_disabled_by_zero(book: ReputationBook) -> None:
    book.observe("C1")
    assert book.forget_older_than(0.0, NOW) == 0
    assert "C1" in book.creators


def test_eviction_prefers_clean_addresses(
    book: ReputationBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reputation_module, "MAX_CREATORS", 5)
    for i in range(5):
        book.observe(f"clean{i}")
    rug(book, "bad")
    book.observe("overflow")
    assert "bad" in book.creators
    assert len(book.creators) <= 5


def test_summary_counts_bad(book: ReputationBook) -> None:
    book.observe("C1")
    rug(book, "C2")
    assert "1" in book.summary() and "rug" in book.summary()


def test_record_defaults_are_harmless() -> None:
    record = CreatorRecord(creator="C")
    assert not record.is_known_bad
    assert MAX_CREATORS > 0
