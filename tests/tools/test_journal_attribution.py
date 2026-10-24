"""Regression (JRN-1): caller-supplied keys cannot change the recorded seat or source.

An escalation body that names ``seat`` or ``source`` must not override the
calling seat or the paper source in the stored payload, through either
``journal.append`` or ``desk.event_emit``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.ids import bind_calling_seat
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.desk.event_emit import EventEmitIn, build_event_emit_tool
from pumpgrok.tools.journal.append import JournalAppendIn, build_journal_append_tool

START = 1469918176.385


async def test_escalation_body_cannot_override_bound_seat(tmp_path: Path) -> None:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    tool = build_journal_append_tool(store, FixtureClock(start=START), tmp_path / "journal")

    with bind_calling_seat("bot-01-scout"):
        out = await tool(
            JournalAppendIn(
                kind="escalation",
                body={"kind": "heartbeat_stale", "seat": "bot-06-exit", "detail": "stop"},
                bot="bot-01-scout",
            )
        )

    stored = store.read()[out.seq - 1]
    assert stored["payload"]["seat"] == "bot-01-scout"
    assert stored["payload"]["detail"] == "stop"
    store.close()


async def test_escalation_body_cannot_replace_source(tmp_path: Path) -> None:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    tool = build_journal_append_tool(store, FixtureClock(start=START), tmp_path / "journal")

    with bind_calling_seat("bot-01-scout"):
        out = await tool(
            JournalAppendIn(
                kind="escalation",
                body={"kind": "heartbeat_stale", "source": "chain", "detail": "x"},
                bot="bot-01-scout",
            )
        )

    stored = store.read()[out.seq - 1]
    assert stored["payload"]["source"] == "paper"
    store.close()


async def test_event_emit_body_cannot_override_bound_seat_or_source(tmp_path: Path) -> None:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    tool = build_event_emit_tool(
        store, FixtureClock(start=START), tmp_path / "journal", "bot-01-scout"
    )

    with bind_calling_seat("bot-01-scout"):
        out = await tool(
            EventEmitIn(
                kind="escalation",
                task_id="t-7",
                payload={
                    "kind": "heartbeat_stale",
                    "seat": "bot-06-exit",
                    "source": "chain",
                    "detail": "y",
                },
            )
        )

    stored = store.read()[out.seq - 1]
    assert stored["payload"]["seat"] == "bot-01-scout"
    assert stored["payload"]["source"] == "paper"
    assert stored["payload"]["detail"] == "y"
    store.close()
