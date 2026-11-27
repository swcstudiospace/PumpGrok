"""RED: journal tools (append/render_report) — TOOL-005.

- seats write only journal_note and escalation (other kinds fail validation)
- render_report writes markdown via tmp+replace and returns a zeroed summary
"""

from __future__ import annotations

import asyncio
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


def _assert_is_file(path: str) -> None:
    assert Path(path).is_file()


async def test_render_report_writes_markdown(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tool = build_render_report_tool(store, FixtureClock(start=START), tmp_path / "reports")
    assert RENDER_REPORT_SPEC.timeout_s == 30.0
    assert RENDER_REPORT_SPEC.rate_limit_key == "ledger"
    out = await tool(RenderReportIn(period="daily"))
    assert out.report_path.endswith(".md")
    _assert_is_file(out.report_path)
    assert out.summary["trades"] == 0
    assert out.summary["open_positions"] == 0
    store.close()


@pytest.mark.parametrize(
    "refs",
    ["SOL-20260201-001", 7, None, [7]],
    ids=["string", "int", "null", "non-string-item"],
)
def test_journal_note_refs_must_be_a_list_of_strings(refs: object) -> None:
    with pytest.raises(ValidationError):
        JournalAppendIn(
            kind="journal_note",
            note_kind="lead",
            bot="bot-01-scout",
            body={"text": "x", "refs": refs},
        )


def test_journal_note_accepts_a_list_of_ref_strings() -> None:
    entry = JournalAppendIn(
        kind="journal_note",
        note_kind="lead",
        bot="bot-01-scout",
        body={"text": "x", "refs": ["SOL-20260201-001"]},
    )
    assert entry.body["refs"] == ["SOL-20260201-001"]


def _fund(store: LedgerStore) -> None:
    store.set_meta("initial_equity_lamports", "1000000000")
    store.set_meta("source", "paper")


def _spend(store: LedgerStore, ts_utc: str, spent: int, key: str) -> None:
    """Spend ``spent`` lamports with no open position: cash falls, peak holds."""
    store.append(
        ts_utc=ts_utc,
        source="paper",
        correlation_id="t",
        idempotency_key=key,
        type="FillRecorded",
        payload={
            "source": "paper",
            "order_id": f"o-{key}",
            "decision_id": f"d-{key}",
            "side": "buy",
            "mint": "So11111111111111111111111111111111111111112",
            "filled_lamports": spent,
            "filled_units": 10,
            "filled_fraction": "1",
            "price_avg": "1",
            "venue_fee_lamports": 0,
            "network_cost_lamports": 0,
            "cash_delta_lamports": -spent,
        },
    )


async def test_render_report_drawdown_is_the_period_max(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _fund(store)
    _spend(store, "2016-07-30T10:00:00.000000Z", 300_000_000, "dd-in-period")
    tool = build_render_report_tool(store, FixtureClock(start=START), tmp_path / "reports")
    out = await tool(RenderReportIn(period="daily"))
    body = await asyncio.to_thread(Path(out.report_path).read_text, encoding="utf-8")
    store.close()
    assert out.summary["max_drawdown_fraction"] == "0.3"
    assert "Max drawdown fraction: 0.3." in body


async def test_render_report_drawdown_carries_in_and_ignores_later_events(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _fund(store)
    # Before the day of START (2016-07-30 22:36 UTC): sets the drawdown the day opens with.
    _spend(store, "2016-07-29T12:00:00.000000Z", 300_000_000, "dd-before")
    # After START: must not be folded into a report pinned to START.
    _spend(store, "2016-07-30T23:59:00.000000Z", 500_000_000, "dd-after")
    tool = build_render_report_tool(store, FixtureClock(start=START), tmp_path / "reports")
    out = await tool(RenderReportIn(period="daily"))
    store.close()
    assert out.summary["max_drawdown_fraction"] == "0.3"
