"""Regression: journal identity and retry durability (review findings 26, 27).

27: entries that differ in any field (including note_kind, and seat/ticket text
    that could blur a delimiter) must never share an idempotency key.
26: a retried append must leave the day file with one complete line for the
    stored seq: restored when a prior export was lost, and never a fragment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.journal.append import (
    JournalAppendIn,
    journal_append_key,
    run_journal_append,
)

TICKET = "SOL-20260101-001"
START = 1469918176.385


def _note(note_kind: str, text: str = "same body", bot: str = "bot-01-scout") -> JournalAppendIn:
    return JournalAppendIn(
        kind="journal_note",
        note_kind=note_kind,
        ticket_id=TICKET,
        body={"text": text},
        bot=bot,
    )


def _read_text_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _read_records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in _read_text_lines(path)]


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _remove(path: Path) -> None:
    path.unlink()


def _overwrite_bytes(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def test_note_kind_changes_the_key() -> None:
    body = {"text": "same"}
    note = journal_append_key("journal_note", "note", TICKET, "bot-01-scout", body)
    verdict = journal_append_key("journal_note", "verdict", TICKET, "bot-01-scout", body)
    assert note != verdict


def test_delimiter_text_cannot_blur_fields() -> None:
    body: dict = {}
    # Seat text embedding a newline and a ticket-shaped suffix must not match
    # the same fields split differently.
    a = journal_append_key("journal_note", "note", None, "bot\n" + TICKET, body)
    b = journal_append_key("journal_note", "note", TICKET, "bot", body)
    assert a != b


def test_none_and_empty_ticket_stay_distinct() -> None:
    body: dict = {}
    assert journal_append_key("escalation", None, None, "s", body) != journal_append_key(
        "escalation", None, "", "s", body
    )


async def test_same_body_different_note_kind_both_persist(tmp_path: Path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    clock = FixtureClock(start=START)
    journal_dir = tmp_path / "journal"
    first = await run_journal_append(_note("note"), store, clock, journal_dir)
    second = await run_journal_append(_note("verdict"), store, clock, journal_dir)
    assert first["seq"] != second["seq"]
    kinds = [
        json.loads(line)["payload"]["note_kind"]
        for line in _read_text_lines(Path(first["journal_path"]))
    ]
    assert kinds == ["note", "verdict"]


async def test_retry_restores_a_lost_export(tmp_path: Path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    clock = FixtureClock(start=START)
    journal_dir = tmp_path / "journal"
    first = await run_journal_append(_note("note"), store, clock, journal_dir)
    path = Path(first["journal_path"])
    _remove(path)  # the ledger row committed but the daily file write was lost
    retry = await run_journal_append(_note("note"), store, clock, journal_dir)
    assert retry["seq"] == first["seq"]
    records = _read_records(path)
    assert [r["seq"] for r in records] == [first["seq"]]


async def test_retry_with_present_line_writes_nothing(tmp_path: Path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    clock = FixtureClock(start=START)
    journal_dir = tmp_path / "journal"
    first = await run_journal_append(_note("note"), store, clock, journal_dir)
    path = Path(first["journal_path"])
    before = _read_bytes(path)
    await run_journal_append(_note("note"), store, clock, journal_dir)
    assert _read_bytes(path) == before


async def test_retry_replaces_a_partial_fragment_with_a_whole_line(tmp_path: Path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    clock = FixtureClock(start=START)
    journal_dir = tmp_path / "journal"
    first = await run_journal_append(_note("note"), store, clock, journal_dir)
    path = Path(first["journal_path"])
    _remove(path)
    # A torn write left a fragment with no terminating newline.
    _overwrite_bytes(path, b'{"seq": 1, "kind": "jour')
    await run_journal_append(_note("note"), store, clock, journal_dir)
    records = _read_records(path)
    assert [r["seq"] for r in records] == [first["seq"]]
    assert _read_bytes(path).endswith(b"\n")
