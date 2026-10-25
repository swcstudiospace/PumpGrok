"""journal.append: seat decision/journal entries into the ledger (TOOL-005).

Seats may write only ``journal_note`` and ``escalation`` (I5); every other
ledger type is adapter/RiskEngine/supervisor/CLI-only and fails input
validation here with the schema. ``note_kind`` is required for
``journal_note`` and follows the ledger ``NoteKind`` vocabulary (no ``halt``;
locked Q4 divergence). Appends are idempotent over
``(kind, ticket_id, sha256(body))`` and export to ``YYYY-MM-DD.jsonl``.
"""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from pumpgrok.core.errors import PermissionDenied
from pumpgrok.core.ids import Clock, ambient_correlation, calling_seat
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.ledger.events import NoteKind
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.tools._common import meta_now

__all__ = [
    "APPEND_SPEC",
    "JournalAppendIn",
    "JournalAppendOut",
    "build_journal_append_tool",
    "journal_append_key",
    "run_journal_append",
]

SEAT_WRITABLE_KINDS: tuple[str, str] = ("journal_note", "escalation")

_NOTE_KINDS: tuple[str, ...] = tuple(k.value for k in NoteKind)


class JournalAppendIn(ToolInput):
    """Seat-attributed journal entry; ``bot`` names the writing seat."""

    kind: Literal["journal_note", "escalation"]
    note_kind: str | None = None
    ticket_id: str | None = Field(default=None, pattern=r"^SOL-\d{8}-\d{3}$")
    body: dict[str, Any] = Field(default_factory=dict)
    bot: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _note_kind_rule(self) -> Self:
        if self.kind == "journal_note":
            if self.note_kind is None:
                raise ValueError("note_kind is required when kind is journal_note")
            if self.note_kind not in _NOTE_KINDS:
                raise ValueError(f"unknown note_kind {self.note_kind!r}")
        elif self.note_kind is not None:
            raise ValueError("note_kind is only valid when kind is journal_note")
        return self


class JournalAppendOut(ToolOutput):
    """Stored seq and the JSONL export path."""

    seq: int = Field(ge=1)
    journal_path: str


APPEND_SPEC = ToolSpec(
    name="journal.append",
    description=(
        "Append a seat decision/journal entry keyed by ticket. Seats write "
        "journal_note and escalation only; every other kind is refused."
    ),
    input_model=JournalAppendIn,
    output_model=JournalAppendOut,
    side_effect=SideEffect.PAPER_WRITE,
    timeout_s=5.0,
    rate_limit_key="ledger",
    idempotent=True,
    backend="pumpgrok.ledger.store.LedgerStore",
)


def journal_append_key(
    kind: str,
    note_kind: str | None,
    ticket_id: str | None,
    seat: str,
    body: dict[str, Any],
) -> str:
    """Derived key: d(kind, note_kind, ticket_id, seat, body).

    The fields are JSON-encoded as one array so that no field's text can be
    read as another field's boundary; ``None`` and ``""`` stay distinct.
    """
    identity = json.dumps(
        [kind, note_kind, ticket_id, seat, body], sort_keys=True, ensure_ascii=True
    )
    return hashlib.sha256(identity.encode("ascii")).hexdigest()[:32]


def _payload_of(inp: JournalAppendIn, seat: str) -> tuple[str, dict[str, Any]]:
    if inp.kind == "journal_note":
        return "JournalNote", {
            "source": "paper",
            "seat": seat,
            "note_kind": inp.note_kind,
            "text": str(inp.body.get("text", "")),
            "refs": list(inp.body.get("refs", [])),
        }
    return "Escalation", {**inp.body, "source": "paper", "seat": seat}


def _journal_file(journal_dir: Path, day: datetime) -> Path:
    """Return the ``YYYY-MM-DD.jsonl`` export path for ``day``'s UTC date."""
    return journal_dir / f"{day.strftime('%Y-%m-%d')}.jsonl"


def _has_seq(data: bytes, seq: int) -> bool:
    """True when ``data`` holds a complete JSONL record whose ``seq`` is ``seq``."""
    for raw in data.splitlines():
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        if isinstance(record, dict) and record.get("seq") == seq:
            return True
    return False


def _export_line(journal_dir: Path, day: datetime, seq: int, line: str) -> Path:
    """Ensure exactly one complete JSONL line for ``seq`` in ``day``'s file.

    A retry whose earlier export was lost finds no such line and writes it; a
    retry that finds it writes nothing. A trailing fragment from an interrupted
    write is cut back to the last newline first, so the new record is whole.
    The exclusive ``flock`` covers the read, the duplicate check and the write,
    so overlapping retries (threads or processes) cannot both append ``seq``.
    Blocking file I/O.
    """
    journal_dir.mkdir(parents=True, exist_ok=True)
    journal_path = _journal_file(journal_dir, day)
    with open(journal_path, "a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)  # released when the handle closes
        handle.seek(0)
        data = handle.read()
        complete = data[: data.rfind(b"\n") + 1]
        if _has_seq(complete, seq):
            return journal_path
        if len(complete) != len(data):
            handle.truncate(len(complete))
        handle.seek(0, os.SEEK_END)
        handle.write((line + "\n").encode("utf-8"))
    return journal_path


async def run_journal_append(
    inp: JournalAppendIn, store: LedgerStore, clock: Clock, journal_dir: Path
) -> dict[str, Any]:
    """Append the event (idempotent) and export the JSONL line."""
    ambient = ambient_correlation()
    correlation = inp.correlation_id or (str(ambient) if ambient else "none")
    bound = calling_seat()
    if bound is not None and inp.bot != bound:
        raise PermissionDenied(
            f"journal.append seat mismatch: calling seat is {bound}",
            tool="journal.append",
            bot=bound,
        )
    seat = bound if bound is not None else inp.bot
    now = datetime.fromtimestamp(clock.now(), UTC)
    key = journal_append_key(inp.kind, inp.note_kind, inp.ticket_id, seat, inp.body)
    event_type, payload = _payload_of(inp, seat)
    try:
        row = store.append(
            ts_utc=now.isoformat(),
            source="paper",
            correlation_id=correlation,
            idempotency_key=key,
            type=event_type,
            payload=payload,
        )
    except sqlite3.IntegrityError:
        existing = store.by_key(key)
        if existing is None:  # pragma: no cover - defensive
            raise
        # A repeat keeps the prior seq and day file; the export is re-checked below.
        seq = int(existing["seq"])
        day = datetime.fromisoformat(str(existing["ts_utc"]))
    else:
        seq = int(row["seq"])
        day = now
    line = json.dumps({"seq": seq, "kind": inp.kind, "payload": payload})
    journal_path = await asyncio.to_thread(_export_line, journal_dir, day, seq, line)
    return JournalAppendOut.model_validate(
        {
            "seq": seq,
            "journal_path": str(journal_path),
            "meta": meta_now("ledger", correlation, clock),
        }
    ).model_dump()


def build_journal_append_tool(store: LedgerStore, clock: Clock, journal_dir: Path) -> Tool:
    """Bind ``journal.append`` to one store, clock and directory."""

    @tool(APPEND_SPEC)
    async def _append(payload: JournalAppendIn) -> dict[str, Any]:
        return await run_journal_append(payload, store, clock, journal_dir)

    return _append
