"""Regression (WR-10): journal idempotency is scoped to the calling seat.

Two seats appending the same kind/ticket_id/body must each record their own
event and seq. Before the fix the idempotency key omitted the seat, so the
second seat's call hit the IntegrityError repeat path and silently returned
the first seat's seq without writing anything.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pumpgrok.core.ids import bind_calling_seat
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.journal.append import JournalAppendIn, build_journal_append_tool

START = 1469918176.385


def _payload(bot: str) -> JournalAppendIn:
    return JournalAppendIn(
        kind="journal_note",
        note_kind="lead",
        ticket_id="SOL-20260201-001",
        body={"text": "saw a launch"},
        bot=bot,
    )


async def test_identical_payload_from_two_seats_records_two_events(
    tmp_path: Path,
) -> None:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    journal_dir = tmp_path / "journal"
    tool = build_journal_append_tool(store, FixtureClock(start=START), journal_dir)

    with bind_calling_seat("bot-01-scout"):
        first = await tool(_payload("bot-01-scout"))
    with bind_calling_seat("bot-02-exec"):
        second = await tool(_payload("bot-02-exec"))

    assert first.seq != second.seq
    assert {first.seq, second.seq} == {1, 2}
    assert store.count() == 2
    store.close()


async def test_same_seat_repeat_still_dedups(tmp_path: Path) -> None:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    journal_dir = tmp_path / "journal"
    tool = build_journal_append_tool(store, FixtureClock(start=START), journal_dir)

    with bind_calling_seat("bot-01-scout"):
        first = await tool(_payload("bot-01-scout"))
        repeat = await tool(_payload("bot-01-scout"))

    assert repeat.seq == first.seq
    assert store.count() == 1
    store.close()
