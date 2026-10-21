"""portfolio.ledger_read: filtered reads over the hash-chained ledger (TOOL-005)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.tools._common import meta_now

__all__ = [
    "LEDGER_READ_SPEC",
    "LedgerReadIn",
    "LedgerReadOut",
    "build_ledger_read_tool",
    "run_ledger_read",
]


class LedgerReadIn(ToolInput):
    """Filters over events in seq order plus the latest snapshot."""

    since_seq: int = Field(default=0, ge=0)
    types: list[str] | None = None
    ticket_id: str | None = Field(default=None, pattern=r"^SOL-\d{8}-\d{3}$")
    source: Literal["paper", "replay", "manual"] | None = None
    limit: int = Field(default=200, ge=1, le=1000)


class LedgerReadOut(ToolOutput):
    """Matching events and the newest snapshot (None when never snapshotted)."""

    events: list[dict] = Field(default_factory=list)
    latest_snapshot: dict | None = None


LEDGER_READ_SPEC = ToolSpec(
    name="portfolio.ledger_read",
    description=(
        "Read append-only ledger events and snapshots with filters. "
        "Read only; the ledger is written by the execution path."
    ),
    input_model=LedgerReadIn,
    output_model=LedgerReadOut,
    side_effect=SideEffect.READ,
    timeout_s=5.0,
    rate_limit_key="ledger",
    backend="pumpgrok.ledger.store.LedgerStore.read",
)


async def run_ledger_read(inp: LedgerReadIn, store: LedgerStore) -> dict:
    """Filter events and fetch the latest snapshot (read-only, no locks)."""
    ambient = ambient_correlation()
    events = store.read(
        since_seq=inp.since_seq,
        types=inp.types,
        ticket_id=inp.ticket_id,
        source=inp.source,
        limit=inp.limit,
    )
    return LedgerReadOut.model_validate(
        {
            "events": events,
            "latest_snapshot": store.latest_snapshot(),
            "meta": meta_now(
                "ledger", inp.correlation_id or (str(ambient) if ambient else None)
            ),
        }
    ).model_dump()


def build_ledger_read_tool(store: LedgerStore) -> Tool:
    """Bind ``portfolio.ledger_read`` to one store (no globals)."""

    @tool(LEDGER_READ_SPEC)
    async def _ledger_read(payload: LedgerReadIn) -> dict:
        return await run_ledger_read(payload, store)

    return _ledger_read
