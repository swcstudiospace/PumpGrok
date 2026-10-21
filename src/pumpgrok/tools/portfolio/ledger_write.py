"""portfolio.ledger_write: adapter-only ledger append (TOOL-005).

Not in any seat roster (``BotManifest`` refuses the grant and the registry
audits the attempt): only the PaperAdapter, ``RiskEngine.check``, the
supervisor and the human CLI call it in-process. Listed so the registry can
audit it. Idempotency comes from the caller-supplied required key with the
store's UNIQUE index; a repeat returns the stored row with ``duplicate``.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field

from pumpgrok.core.ids import Clock, ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.ledger.events import EventType
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.tools._common import meta_now

__all__ = [
    "LEDGER_WRITE_SPEC",
    "LedgerWriteIn",
    "LedgerWriteOut",
    "build_ledger_write_tool",
    "run_ledger_write",
]


class LedgerWriteIn(ToolInput):
    """One ledger event; ``type`` is a CamelCase R32 event, ``key`` required."""

    type: EventType
    source: Literal["paper", "replay", "manual"]
    payload: dict[str, Any] = Field(default_factory=dict)
    ticket_id: str | None = Field(default=None, pattern=r"^SOL-\d{8}-\d{3}$")
    idempotency_key: str = Field(min_length=1, max_length=128)


class LedgerWriteOut(ToolOutput):
    """Stored row; ``duplicate`` when the key was already present."""

    seq: int = Field(ge=1)
    hash: str
    duplicate: bool


LEDGER_WRITE_SPEC = ToolSpec(
    name="portfolio.ledger_write",
    description=(
        "Append one ledger event through the store. Adapter-only: never in a "
        "seat roster; the registry refuses every seat grant."
    ),
    input_model=LedgerWriteIn,
    output_model=LedgerWriteOut,
    side_effect=SideEffect.PAPER_WRITE,
    timeout_s=5.0,
    rate_limit_key="ledger",
    idempotent=True,
    backend="pumpgrok.ledger.store.LedgerStore.append",
)


async def run_ledger_write(inp: LedgerWriteIn, store: LedgerStore, clock: Clock) -> dict[str, Any]:
    """Append the validated event; a duplicate key replays the stored row."""
    ambient = ambient_correlation()
    correlation = inp.correlation_id or (str(ambient) if ambient else "none")
    ts_utc = datetime.fromtimestamp(clock.now(), UTC).isoformat()
    try:
        row = store.append(
            ts_utc=ts_utc,
            source=inp.source,
            correlation_id=correlation,
            idempotency_key=inp.idempotency_key,
            type=inp.type.value,
            payload=inp.payload,
        )
    except sqlite3.IntegrityError:
        existing = store.by_key(inp.idempotency_key)
        if existing is None:  # pragma: no cover - defensive; key collision lost a race
            raise
        return LedgerWriteOut.model_validate(
            {
                "seq": existing["seq"],
                "hash": existing["hash"],
                "duplicate": True,
                "meta": meta_now("ledger", correlation, clock),
            }
        ).model_dump()
    return LedgerWriteOut.model_validate(
        {
            "seq": row["seq"],
            "hash": row["hash"],
            "duplicate": False,
            "meta": meta_now("ledger", correlation, clock),
        }
    ).model_dump()


def build_ledger_write_tool(store: LedgerStore, clock: Clock) -> Tool:
    """Bind ``portfolio.ledger_write`` to one store and clock (no globals)."""

    @tool(LEDGER_WRITE_SPEC)
    async def _ledger_write(payload: LedgerWriteIn) -> dict[str, Any]:
        return await run_ledger_write(payload, store, clock)

    return _ledger_write
