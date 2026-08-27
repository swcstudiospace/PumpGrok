"""Память о создателях: один и тот же деплойер не должен сливать нас дважды."""

import time

import pytest

from src.reputation import MAX_CREATORS, CreatorRecord, ReputationBook


@pytest.fixture
def book() -> ReputationBook:
    return ReputationBook()


def rug(book: ReputationBook, creator: str = "C1", pct: float = -85.0) -> None:
    book.record_close(creator, pnl_sol=-0.4, pnl_pct=pct, rug_loss_pct=60.0)


# --- учёт -----------------------------------------------------------------


def test_unknown_creator_is_not_blocked(book):
    assert book.verdict("новый", block_after_rugs=1) is None
    assert book.verdict(None, block_after_rugs=1) is None


def test_rug_blocks_next_token(book):
    rug(book)
    verdict = book.verdict("C1", block_after_rugs=1)
    assert verdict is not None
    assert "сливал" in verdict


def test_moderate_loss_is_not_a_rug(book):
    book.record_close("C1", pnl_sol=-0.1, pnl_pct=-35.0, rug_loss_pct=60.0)
    assert book.creators["C1"].rugs == 0
    assert book.verdict("C1", block_after_rugs=1) is None


def test_rug_threshold_boundary(book):
    book.record_close("C1", pnl_sol=-0.3, pnl_pct=-60.0, rug_loss_pct=60.0)
    assert book.creators["C1"].rugs == 1
    book.record_close("C2", pnl_sol=-0.3, pnl_pct=-59.9, rug_loss_pct=60.0)
    assert book.creators["C2"].rugs == 0


def test_tolerance_configurable(book):
    rug(book)
    assert book.verdict("C1", block_after_rugs=2) is None    # одного слива мало
    rug(book)
    assert book.verdict("C1", block_after_rugs=2) is not None


def test_zero_disables_blocking(book):
    rug(book)
    assert book.verdict("C1", block_after_rugs=0) is None


def test_profit_does_not_erase_history(book):
    """Один удачный выход не отменяет того, что адрес уже сливал."""
    rug(book)
    book.record_close("C1", pnl_sol=+1.0, pnl_pct=+150.0, rug_loss_pct=60.0)
    assert book.verdict("C1", block_after_rugs=1) is not None
    assert book.creators["C1"].realized_pnl_sol == pytest.approx(0.6)


def test_counters_accumulate(book):
    book.observe("C1")
    book.observe("C1")
    book.record_open("C1")
    book.record_close("C1", pnl_sol=0.2, pnl_pct=40.0, rug_loss_pct=60.0)
    record = book.creators["C1"]
    assert (record.tokens_seen, record.tokens_bought, record.closed) == (2, 1, 1)
    assert record.worst_pnl_pct == 0.0        # минусов не было


def test_worst_result_is_remembered(book):
    book.record_close("C1", pnl_sol=-0.1, pnl_pct=-20.0, rug_loss_pct=60.0)
    book.record_close("C1", pnl_sol=-0.3, pnl_pct=-90.0, rug_loss_pct=60.0)
    book.record_close("C1", pnl_sol=-0.1, pnl_pct=-10.0, rug_loss_pct=60.0)
    assert book.creators["C1"].worst_pnl_pct == -90.0


# --- диск -----------------------------------------------------------------


def test_survives_restart(tmp_path):
    path = tmp_path / "creators.json"
    book = ReputationBook()
    rug(book)
    book.save(path)

    reloaded = ReputationBook.load(path)
    assert reloaded.verdict("C1", block_after_rugs=1) is not None


def test_missing_file_is_empty_book(tmp_path):
    assert ReputationBook.load(tmp_path / "нет.json").creators == {}


def test_corrupt_file_does_not_crash(tmp_path):
    path = tmp_path / "creators.json"
    path.write_text("{не json")
    assert ReputationBook.load(path).creators == {}


def test_save_leaves_no_temp_files(tmp_path):
    path = tmp_path / "creators.json"
    book = ReputationBook()
    rug(book)
    book.save(path)
    book.save(path)
    assert [p.name for p in tmp_path.iterdir() if ".tmp" in p.name] == []


# --- обслуживание ---------------------------------------------------------


def test_forgets_stale_but_keeps_rugs(book):
    book.observe("чистый")
    rug(book, "плохой")
    old = time.time() - 100 * 86_400
    for record in book.creators.values():
        record.last_seen = old

    forgotten = book.forget_older_than(days=30)
    assert forgotten == 1
    assert "чистый" not in book.creators
    assert "плохой" in book.creators          # сливы не забываем


def test_forget_disabled_by_zero(book):
    book.observe("C1")
    book.creators["C1"].last_seen = 0.0
    assert book.forget_older_than(days=0) == 0
    assert "C1" in book.creators


def test_eviction_prefers_clean_addresses(book, monkeypatch):
    monkeypatch.setattr("src.reputation.MAX_CREATORS", 5)
    rug(book, "плохой")
    for index in range(20):
        book.observe(f"чистый{index}")
    assert len(book.creators) <= 5
    assert "плохой" in book.creators


def test_summary_counts_bad(book):
    book.observe("C1")
    rug(book, "C2")
    assert "со сливами 1" in book.summary()


def test_record_defaults_are_harmless():
    record = CreatorRecord(creator="C")
    assert not record.is_known_bad
    assert MAX_CREATORS > 0
