"""Regression (WR-08): an idempotent journal.append repeat must not re-export.

A repeat of a stored intent returns the prior seq and journal path and writes
no second JSONL line, so JSONL replays and report folds count the entry once.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.journal.append import JournalAppendIn, build_journal_append_tool

START = 1469918176.385


def _payload() -> JournalAppendIn:
    return JournalAppendIn(
        kind="journal_note",
        note_kind="lead",
        ticket_id="SOL-20260201-001",
        body={"text": "saw a launch"},
        bot="bot-01-scout",
    )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _jsonl_names(journal_dir: Path) -> list[str]:
    return sorted(p.name for p in journal_dir.glob("*.jsonl"))


async def test_repeat_append_returns_prior_result_without_second_line(tmp_path: Path) -> None:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    journal_dir = tmp_path / "journal"
    tool = build_journal_append_tool(store, FixtureClock(start=START), journal_dir)

    first = await tool(_payload())
    journal_file = Path(first.journal_path)
    before = _read_text(journal_file)

    second = await tool(_payload())

    assert second.seq == first.seq
    assert second.journal_path == first.journal_path
    assert _read_text(journal_file) == before
    assert len(before.splitlines()) == 1
    assert store.count() == 1
    store.close()


async def test_repeat_on_later_day_exports_nothing(tmp_path: Path) -> None:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    journal_dir = tmp_path / "journal"
    first_tool = build_journal_append_tool(store, FixtureClock(start=START), journal_dir)
    first = await first_tool(_payload())
    names_before = _jsonl_names(journal_dir)

    # Same derived key, next UTC day: the repeat must not open a new day file.
    later_tool = build_journal_append_tool(store, FixtureClock(start=START + 86400), journal_dir)
    repeat = await later_tool(_payload())

    assert repeat.seq == first.seq
    assert repeat.journal_path == first.journal_path
    assert _jsonl_names(journal_dir) == names_before
    assert len(_read_text(Path(first.journal_path)).splitlines()) == 1
    store.close()
