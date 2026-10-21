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
import hashlib
import json
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


def journal_append_key(kind: str, ticket_id: str | None, body: dict[str, Any]) -> str:
    """Derived key: d(kind, ticket_id, sha256(body))."""
    digest = hashlib.sha256(
        f"{kind}\n{ticket_id or ''}\n{json.dumps(body, sort_keys=True)}".encode()
    ).hexdigest()
    return digest[:32]


def _payload_of(inp: JournalAppendIn, seat: str) -> tuple[str, dict[str, Any]]:
    if inp.kind == "journal_note":
        return "JournalNote", {
            "source": "paper",
            "seat": seat,
            "note_kind": inp.note_kind,
            "text": str(inp.body.get("text", "")),
            "refs": list(inp.body.get("refs", [])),
        }
    return "Escalation", {"source": "paper", "seat": seat, **inp.body}


def _journal_file(journal_dir: Path, day: datetime) -> Path:
    """Return the ``YYYY-MM-DD.jsonl`` export path for ``day``'s UTC date."""
    return journal_dir / f"{day.strftime('%Y-%m-%d')}.jsonl"


def _export_line(journal_dir: Path, now: datetime, line: str) -> Path:
    """Append one JSONL line to the day's journal file (blocking file I/O)."""
    journal_dir.mkdir(parents=True, exist_ok=True)
    journal_path = _journal_file(journal_dir, now)
    with open(journal_path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
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
    key = journal_append_key(inp.kind, inp.ticket_id, inp.body)
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
        # A repeat returns the prior result: same seq, same day file, no write.
        seq = int(existing["seq"])
        prior_day = datetime.fromisoformat(str(existing["ts_utc"]))
        journal_path = _journal_file(journal_dir, prior_day)
    else:
        seq = int(row["seq"])
        line = json.dumps({"seq": seq, "kind": inp.kind, "payload": payload})
        journal_path = await asyncio.to_thread(_export_line, journal_dir, now, line)
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
