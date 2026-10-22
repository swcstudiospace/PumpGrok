"""Shared shapes for the typed READ tools (Phase 3, wave 2).

Kept here so the twelve market/onchain wrappers share one mint validator,
one ``ToolMeta`` constructor and the catalog retry policies (j4/j5) instead
of duplicating them per module. Wall-clock reads go through the replay
``Clock`` (never ``datetime.now``); only ``replay/clock.py`` may touch it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import Field

from pumpgrok.core.tool import RetryPolicy, ToolMeta
from pumpgrok.ledger.reducer import LedgerState, initial_state, reduce
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import Clock

MINT_RE = r"^[1-9A-HJ-NP-Za-km-z]{32,44}$"

MintStr = Annotated[str, Field(pattern=MINT_RE)]

SOLANA_RPC_SOURCE = "solana_rpc"

LAMPORTS_PER_SOL = 1_000_000_000
UNITS_PER_TOKEN = 1_000_000

J4 = RetryPolicy(attempts=3, base_s=0.5, max_s=4.0)
J5 = RetryPolicy(attempts=3, base_s=0.5, max_s=5.0)


def utcnow(clock: Clock) -> datetime:
    """Now via the injected replay clock (never wall time)."""
    return datetime.fromtimestamp(clock.now(), UTC)


def meta_now(source: str, correlation_id: str | None, clock: Clock) -> ToolMeta:
    """Fresh (non-stale) envelope stamped at call time."""
    return ToolMeta(
        source=source,
        fetched_at=utcnow(clock),
        freshness_s=0.0,
        correlation_id=correlation_id or "none",
    )


def fold_current_state(store: LedgerStore, clock: Clock) -> LedgerState:
    """Current ledger state: genesis from meta, then every event (same fold as the engine).

    Read tools use this instead of the newest snapshot, which can lag the
    ledger and never carried an ``equity_lamports`` key.
    """
    meta_equity = store.get_meta("initial_equity_lamports")
    initial = int(meta_equity) if meta_equity is not None else 0
    source = store.get_meta("source") or "paper"
    day_utc = utcnow(clock).strftime("%Y-%m-%d")
    state = initial_state(source=source, initial_equity_lamports=initial, day_utc=day_utc)
    for event in store.read(limit=None):
        state = reduce(state, event)
    return state
