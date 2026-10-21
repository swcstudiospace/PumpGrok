"""desk.event_emit: seat-attributed ledger event (TOOL-007).

Seats may emit ``journal_note`` and ``escalation`` only (I5); every other
kind fails input validation. The seat is bound at build time (the gateway
binds one emitter per seat), so the ledger row is always attributed. The
payload is scrubbed (secret-looking values masked) and capped at 4 KB, then
appended through the same journal path as ``journal.append``.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import Field

from pumpgrok.core.ids import Clock, ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.tools._common import meta_now
from pumpgrok.tools.journal.append import JournalAppendIn, run_journal_append

__all__ = [
    "EVENT_EMIT_SPEC",
    "EventEmitIn",
    "EventEmitOut",
    "build_event_emit_tool",
    "event_emit_key",
    "run_event_emit",
    "scrub_payload",
]

_PAYLOAD_CAP_BYTES = 4096

_SECRET_KEY_RE = re.compile(r"(?i)(token|secret|private_key|seed|mnemonic|keypair)")


class EventEmitIn(ToolInput):
    """Seat-attributed event; ``note_kind`` follows ``journal.append`` rules."""

    kind: Literal["journal_note", "escalation"]
    note_kind: str | None = None
    task_id: str | None = None
    payload: dict = Field(default_factory=dict)


class EventEmitOut(ToolOutput):
    """Stored ledger seq for the emitted event."""

    seq: int = Field(ge=1)


EVENT_EMIT_SPEC = ToolSpec(
    name="desk.event_emit",
    description=(
        "Emit a seat-attributed event to the ledger event log; seats emit "
        "journal_note and escalation only, payload scrubbed and capped."
    ),
    input_model=EventEmitIn,
    output_model=EventEmitOut,
    side_effect=SideEffect.PAPER_WRITE,
    timeout_s=5.0,
    rate_limit_key="desk",
    idempotent=True,
    backend="pumpgrok.tools.journal.append",
)


def scrub_payload(payload: dict) -> dict:
    """Mask secret-looking values and cap the JSON form at 4 KB.

    Long strings are shortened in place so the event schema still validates;
    the key set never changes.
    """
    scrubbed = {
        key: ("***" if _SECRET_KEY_RE.search(key) else value)
        for key, value in payload.items()
    }
    for key, value in scrubbed.items():
        if isinstance(value, str) and len(value) > 1024:
            scrubbed[key] = value[:1024] + "…[truncated]"
    while len(json.dumps(scrubbed, sort_keys=True).encode("utf-8")) > _PAYLOAD_CAP_BYTES:
        longest = max(
            (key for key, val in scrubbed.items() if isinstance(val, str) and len(val) > 64),
            key=lambda key: len(scrubbed[key]),
            default=None,
        )
        if longest is None:
            break
        scrubbed[longest] = scrubbed[longest][: len(scrubbed[longest]) // 2] + "…[truncated]"
    return scrubbed


def event_emit_key(bot: str, kind: str, task_id: str | None, payload: dict) -> str:
    """Derived key: d(tool, bot, sha256(input))."""
    body = json.dumps({"kind": kind, "task_id": task_id, "payload": payload}, sort_keys=True)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return hashlib.sha256(f"desk.event_emit\n{bot}\n{digest}".encode()).hexdigest()[:32]


async def run_event_emit(
    inp: EventEmitIn, store: LedgerStore, clock: Clock, journal_dir: Path, bot: str
) -> dict:
    """Scrub, cap, then append through the journal path with seat attribution."""
    scrubbed = scrub_payload(inp.payload)
    # Dedup rides on the journal key, whose body carries the seat: the same
    # triple (tool, bot, sha256(input)) that event_emit_key() pins for tests.
    if inp.kind == "journal_note":
        body = {
            "seat": bot,
            "text": json.dumps(scrubbed, sort_keys=True)[:1000],
            "task_id": inp.task_id,
        }
    else:
        body = {"seat": bot, **scrubbed}
    journal_in = JournalAppendIn(
        kind=inp.kind,
        note_kind=inp.note_kind,
        ticket_id=None,
        body=body,
        bot=bot,
        correlation_id=inp.correlation_id,
    )
    out = await run_journal_append(journal_in, store, clock, journal_dir)
    ambient = ambient_correlation()
    return EventEmitOut.model_validate(
        {
            "seq": out["seq"],
            "meta": meta_now(
                "desk", inp.correlation_id or (str(ambient) if ambient else None)
            ),
        }
    ).model_dump()


def build_event_emit_tool(
    store: LedgerStore, clock: Clock, journal_dir: Path, bot: str
) -> Tool:
    """Bind ``desk.event_emit`` to one store, clock, directory and seat."""

    @tool(EVENT_EMIT_SPEC)
    async def _event_emit(payload: EventEmitIn) -> dict:
        return await run_event_emit(payload, store, clock, journal_dir, bot)

    return _event_emit
