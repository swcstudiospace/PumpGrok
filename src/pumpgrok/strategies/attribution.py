"""Per-strategy P&L attribution folded from the ledger, against the desk total (STR-03).

The desk total is the ledger's own net: the reducer folds every row from the opening equity
recorded in the ledger's meta, and equity.net_lamports values the window. Money is integer
lamports throughout.

attribute() walks the rows in order. Each row's change in equity is attributed to one
bucket: the strategy its ticket is attributed to in strategy_ticket_refs, or the desk. A row
names its ticket directly (PositionOpened carries ticket_id); a row that names only its mint
(a fill, a mark, a close) takes the ticket of the position open on that mint. The buckets
telescope to the desk total exactly, and attribute() checks that before it returns.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pumpgrok.backtest.equity import equity_lamports, net_lamports
from pumpgrok.ledger.reducer import LedgerState, initial_state, reduce
from pumpgrok.ledger.store import LedgerStore

__all__ = [
    "UNATTRIBUTED",
    "Attribution",
    "AttributionError",
    "attribute",
    "desk_genesis",
    "desk_net_lamports",
]

#: The bucket for every row whose ticket belongs to no strategy, the desk's own P&L.
UNATTRIBUTED = "desk"


class AttributionError(ValueError):
    """The ledger cannot be folded for attribution, or the buckets miss the desk total."""


@dataclass(frozen=True)
class Attribution:
    """Per-strategy realized lamports and the desk total they must fold to."""

    per_strategy: dict[str, int] = field(default_factory=dict)
    desk_total_lamports: int = 0


def desk_genesis(store: LedgerStore) -> LedgerState:
    """The ledger's opening state, from the initial equity recorded in its meta."""
    meta = store.get_meta("initial_equity_lamports")
    if meta is None:
        raise AttributionError("ledger holds no initial_equity_lamports meta")
    return initial_state(source="replay", initial_equity_lamports=int(meta), day_utc="")


def desk_net_lamports(store: LedgerStore) -> int:
    """The desk's net realized lamports over every row of the ledger."""
    return net_lamports(desk_genesis(store), store.read(limit=None))


def _ticket_of(payload: Mapping[str, Any], open_tickets: Mapping[str, str]) -> str:
    explicit = str(payload.get("ticket_id", "") or "")
    if explicit:
        return explicit
    mint = str(payload.get("mint", "") or "")
    return open_tickets.get(mint, "") if mint else ""


def _track_open(row_type: str, payload: Mapping[str, Any], open_tickets: dict[str, str]) -> None:
    mint = str(payload.get("mint", "") or "")
    if not mint:
        return
    if row_type == "PositionOpened":
        open_tickets[mint] = str(payload.get("ticket_id", "") or "")
    elif row_type == "PositionClosed":
        open_tickets.pop(mint, None)


def attribute(
    genesis: LedgerState,
    rows: Sequence[Mapping[str, Any]],
    refs: Mapping[str, str],
    *,
    strategy_ids: Sequence[str] = (),
) -> Attribution:
    """Fold the rows from genesis, attributing each row's equity change to one bucket.

    refs maps a ticket id to its strategy id. Every id in strategy_ids gets a bucket even when
    it has no rows, so an idle strategy reads zero rather than missing.
    """
    per: dict[str, int] = {strategy_id: 0 for strategy_id in strategy_ids}
    per.setdefault(UNATTRIBUTED, 0)
    open_tickets: dict[str, str] = {}
    state = genesis
    for row in rows:
        row_type = str(row.get("type", ""))
        payload = row.get("payload") or {}
        before = equity_lamports(state)
        state = reduce(state, row)
        delta = equity_lamports(state) - before
        ticket = _ticket_of(payload, open_tickets)
        bucket = refs.get(ticket, UNATTRIBUTED) if ticket else UNATTRIBUTED
        per[bucket] = per.get(bucket, 0) + delta
        _track_open(row_type, payload, open_tickets)
    total = equity_lamports(state) - equity_lamports(genesis)
    if sum(per.values()) != total:
        raise AttributionError("attributed buckets do not fold to the desk total")
    return Attribution(per_strategy=per, desk_total_lamports=total)
