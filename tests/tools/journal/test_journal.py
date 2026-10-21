"""RED: journal tools (append/render_report) — TOOL-005.

- seats write only journal_note and escalation (other kinds fail validation)
- render_report writes markdown via tmp+replace and returns a zeroed summary
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import pytest
from pydantic import ValidationError

from pumpgrok.core.side_effect import SideEffect
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.journal.append import (
    APPEND_SPEC,
    JournalAppendIn,
    build_journal_append_tool,
)
from pumpgrok.tools.journal.render_report import (
    RENDER_REPORT_SPEC,
    RenderReportIn,
    build_render_report_tool,
)

START = 1469918176.385


def _store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(str(tmp_path / "ledger.sqlite"))


def test_append_spec() -> None:
    assert APPEND_SPEC.side_effect is SideEffect.PAPER_WRITE
    assert APPEND_SPEC.timeout_s == 5.0
    assert APPEND_SPEC.rate_limit_key == "ledger"
    assert APPEND_SPEC.idempotent is True


def test_append_rejects_non_seat_kinds() -> None:
    with pytest.raises(ValidationError):
        JournalAppendIn(kind="OrderPlaced", bot="bot-01-scout", body={})
    with pytest.raises(ValidationError):
        JournalAppendIn(kind="FillRecorded", bot="bot-01-scout", body={})


def test_append_requires_note_kind_for_journal_note() -> None:
    with pytest.raises(ValidationError):
        JournalAppendIn(kind="journal_note", bot="bot-01-scout", body={"text": "x"})


async def test_append_journal_note_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tool = build_journal_append_tool(store, FixtureClock(start=START), tmp_path / "journal")
    out = await tool(
        JournalAppendIn(
            kind="journal_note",
            note_kind="lead",
            ticket_id="SOL-20260201-001",
            body={"text": "saw a launch"},
            bot="bot-01-scout",
        )
    )
    assert out.seq == 1
    assert out.journal_path.endswith(".jsonl")
    assert store.count() == 1
    store.close()


async def test_render_report_writes_markdown(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tool = build_render_report_tool(store, FixtureClock(start=START), tmp_path / "reports")
    assert RENDER_REPORT_SPEC.timeout_s == 30.0
    assert RENDER_REPORT_SPEC.rate_limit_key == "ledger"
    out = await tool(RenderReportIn(period="daily"))
    assert out.report_path.endswith(".md")
    assert Path(out.report_path).is_file()
    assert out.summary["trades"] == 0
    assert out.summary["open_positions"] == 0
    store.close()
