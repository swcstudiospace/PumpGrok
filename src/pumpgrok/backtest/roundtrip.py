"""Round trips and the per-strategy breakdown (BT-09), folded from ledger rows.

A round trip is the fills of one position lifecycle on one mint. A lifecycle opens on the first
buy of a mint with no open position and closes when the units it holds return to zero, so a
partial sell stays in the round trip it reduces. Only a closed round trip carries realized P&L;
an open one carries its mark.

Realized P&L is the sum of the cash deltas of the lifecycle's fills. The ATA deposit is debited
inside the opening buy's cash (within its network cost) and credited back inside the closing
sell's cash, so the two cancel: the refund is an asset returned, not profit. While a position
stays open its deposit sits in its cost basis, and its mark is reducer.position_value_lamports.

round_trips() consumes rows in the read() shape that backtest/equity.py folds. It reads no ledger
itself. Ticket-to-strategy references are passed in. A fill whose ticket is empty or has no
reference belongs to UNATTRIBUTED. Money stays integer lamports.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pumpgrok.ledger.reducer import initial_state, position_value_lamports, reduce

__all__ = ["UNATTRIBUTED", "OpenTrip", "RoundTrip", "RoundTrips", "breakdown", "round_trips"]

#: The strategy key for every round trip whose ticket has no strategy reference.
UNATTRIBUTED = "unattributed"


@dataclass(frozen=True)
class RoundTrip:
    """One closed position lifecycle; realized_lamports is net of fees and the refunded deposit."""

    mint: str
    ticket_id: str
    strategy: str
    opened_seq: int
    closed_seq: int
    fill_count: int
    realized_lamports: int


@dataclass(frozen=True)
class OpenTrip:
    """A lifecycle still open at window end: no realized P&L, only its mark_lamports."""

    mint: str
    ticket_id: str
    strategy: str
    opened_seq: int
    fill_count: int
    mark_lamports: int


@dataclass(frozen=True)
class RoundTrips:
    """Every lifecycle in a window: closed round trips and positions still open at its end."""

    closed: tuple[RoundTrip, ...]
    open_positions: tuple[OpenTrip, ...]


@dataclass
class _Lifecycle:
    mint: str
    opened_seq: int
    ticket_id: str = ""
    units: int = 0
    cash: int = 0
    fills: int = 0


def round_trips(
    rows: Sequence[Mapping[str, Any]],
    ticket_refs: Mapping[str, str] | None = None,
) -> RoundTrips:
    """Group ledger rows into closed and open round trips, in ledger order.

    Raises ValueError on a fill the lifecycle rules cannot place: a sell with no open position, a
    sell of more units than are held, a fill that moves no units, an unknown side, or an open
    lifecycle the reducer holds no position for.
    """
    refs = dict(ticket_refs or {})
    live: dict[str, _Lifecycle] = {}
    closed: list[RoundTrip] = []
    state = initial_state(source="paper", initial_equity_lamports=0, day_utc="")
    for row in rows:
        state = reduce(state, row)
        row_type = str(row.get("type", ""))
        seq = int(row.get("seq", 0))
        payload = _payload(row)
        mint = str(payload.get("mint", ""))
        if row_type == "FillRecorded":
            _apply_fill(live, closed, refs, seq, mint=mint, payload=payload)
        elif row_type == "PositionOpened" and mint in live:
            live[mint].ticket_id = str(payload.get("ticket_id", "") or "")
    open_positions: list[OpenTrip] = []
    for lifecycle in live.values():
        position = state.positions.get(lifecycle.mint)
        if position is None:
            raise ValueError(f"open lifecycle on {lifecycle.mint} has no position in the ledger")
        open_positions.append(
            OpenTrip(
                mint=lifecycle.mint,
                ticket_id=lifecycle.ticket_id,
                strategy=_strategy(lifecycle.ticket_id, refs),
                opened_seq=lifecycle.opened_seq,
                fill_count=lifecycle.fills,
                mark_lamports=position_value_lamports(position),
            )
        )
    return RoundTrips(closed=tuple(closed), open_positions=tuple(open_positions))


def breakdown(book: RoundTrips, total: int) -> dict[str, int]:
    """Realized lamports per strategy key over the closed round trips.

    total is the unsplit desk total the caller supplies. The keys must sum to it exactly, or this
    raises ValueError. Open positions have no realized P&L and are not split here.
    """
    per: dict[str, int] = {}
    for trip in book.closed:
        per[trip.strategy] = per.get(trip.strategy, 0) + trip.realized_lamports
    split = sum(per.values())
    if split != total:
        raise ValueError(f"per-strategy realized {split} does not sum to desk total {total}")
    return dict(sorted(per.items()))


def _apply_fill(
    live: dict[str, _Lifecycle],
    closed: list[RoundTrip],
    refs: Mapping[str, str],
    seq: int,
    *,
    mint: str,
    payload: Mapping[str, Any],
) -> None:
    side = str(payload.get("side", ""))
    units = _int(payload, "filled_units")
    cash = _int(payload, "cash_delta_lamports")
    if side == "buy":
        if units <= 0:
            raise ValueError(f"buy fill at seq {seq} on {mint} moves no units")
        lifecycle = live.get(mint)
        if lifecycle is None:
            lifecycle = _Lifecycle(mint=mint, opened_seq=seq)
            live[mint] = lifecycle
        lifecycle.units += units
        lifecycle.cash += cash
        lifecycle.fills += 1
        return
    if side != "sell":
        raise ValueError(f"fill at seq {seq} on {mint} has unknown side {side!r}")
    lifecycle = live.get(mint)
    if lifecycle is None:
        raise ValueError(f"sell fill at seq {seq} on {mint} has no open position")
    if units <= 0 or units > lifecycle.units:
        raise ValueError(f"sell fill at seq {seq} on {mint} does not match the units held")
    lifecycle.units -= units
    lifecycle.cash += cash
    lifecycle.fills += 1
    if lifecycle.units == 0:
        del live[mint]
        closed.append(
            RoundTrip(
                mint=mint,
                ticket_id=lifecycle.ticket_id,
                strategy=_strategy(lifecycle.ticket_id, refs),
                opened_seq=lifecycle.opened_seq,
                closed_seq=seq,
                fill_count=lifecycle.fills,
                realized_lamports=lifecycle.cash,
            )
        )


def _strategy(ticket_id: str, refs: Mapping[str, str]) -> str:
    if not ticket_id:
        return UNATTRIBUTED
    return refs.get(ticket_id, UNATTRIBUTED)


def _payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = row.get("payload")
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise ValueError("ledger row carries no payload mapping")
    return payload


def _int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key, 0)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"fill row carries non-integer {key}")
    return value
