<<<<<<< HEAD
"""Fill grouping into round trips (BT-09; CONTEXT D-02).

Each fill is a signed cash movement on one mint key: a "buy" spends
lamports (entry), a "sell" receives lamports (exit). Fills group by key
in input order; consecutive buys before the first sell accumulate into
one open trip, partial sells fold into the same open trip, and a sell
closes it. A trip left open at the end is flagged ``unclosed`` and its
open entry basis is not counted as realized. Money stays integer
lamports throughout.
=======
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
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

<<<<<<< HEAD
__all__ = [
    "RoundTrip",
    "RoundTripFill",
    "RoundTripsResult",
    "group_round_trips",
    "per_strategy_breakdown",
]


@dataclass(frozen=True)
class RoundTripFill:
    """One signed fill: side in {"buy", "sell"}, lamports positive amount."""

    key: str
    side: str
    lamports: int
    strategy_id: str = ""

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            raise ValueError(f"side must be buy or sell, found {self.side!r}")
        if not self.key:
            raise ValueError("a fill names a mint key")
        if isinstance(self.lamports, bool) or not isinstance(self.lamports, int):
            raise ValueError("lamports must be integer lamports")
        if self.lamports < 0:
            raise ValueError("lamports must not be negative")
=======
from pumpgrok.ledger.reducer import initial_state, position_value_lamports, reduce

__all__ = ["UNATTRIBUTED", "OpenTrip", "RoundTrip", "RoundTrips", "breakdown", "round_trips"]

#: The strategy key for every round trip whose ticket has no strategy reference.
UNATTRIBUTED = "unattributed"
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687


@dataclass(frozen=True)
class RoundTrip:
<<<<<<< HEAD
    """One entry-to-exit trip on a mint key.

    realized_net_lamports: exits minus entries for closed trips; for an
    unclosed trip it is exits minus entries so far (open basis included),
    with ``unclosed`` True so callers do not mistake it for realized.
    """

    key: str
    strategy_id: str
    entry_lamports: int
    exit_lamports: int
    realized_net_lamports: int
    unclosed: bool


@dataclass(frozen=True)
class RoundTripsResult:
    """All trips grouped from fills, plus win/loss counts over closed trips."""

    trips: tuple[RoundTrip, ...]
    closed: int
    unclosed_count: int
    wins: int
    losses: int
    total_realized_net_lamports: int

    @property
    def total_net_lamports(self) -> int:
        """Sum of realized nets over closed trips only."""
        return sum(trip.realized_net_lamports for trip in self.trips if not trip.unclosed)


def group_round_trips(fills: Sequence[RoundTripFill]) -> RoundTripsResult:
    """Group fills by mint key into round trips.

    Partial exits fold into the open trip; a sell with no preceding buy
    opens and immediately closes its own trip (unusual, never dropped).
    """
    open_trips: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    closed: list[RoundTrip] = []
    for index, fill in enumerate(fills):
        state = open_trips.get(fill.key)
        if state is None:
            state = {
                "entry": 0,
                "exit": 0,
                "strategy_id": fill.strategy_id,
                "open": False,
            }
            open_trips[fill.key] = state
            order.append(fill.key)
        if fill.side == "buy":
            state["entry"] = int(state["entry"]) + fill.lamports
            state["open"] = True
        else:
            state["exit"] = int(state["exit"]) + fill.lamports
            entry = int(state["entry"])
            exit_total = int(state["exit"])
            # Partial exits fold: consecutive sells on the same key belong
            # to one trip; the trip closes on the last of the run.
            following = fills[index + 1] if index + 1 < len(fills) else None
            if following is not None and following.key == fill.key and following.side == "sell":
                continue
            closed.append(
                RoundTrip(
                    key=fill.key,
                    strategy_id=str(state["strategy_id"]),
                    entry_lamports=entry,
                    exit_lamports=exit_total,
                    realized_net_lamports=exit_total - entry,
                    unclosed=False,
                )
            )
            state["entry"] = 0
            state["exit"] = 0
            state["open"] = False
    trips: list[RoundTrip] = list(closed)
    for key in order:
        state = open_trips[key]
        if bool(state["open"]) or int(state["entry"]) > 0:
            trips.append(
                RoundTrip(
                    key=key,
                    strategy_id=str(state["strategy_id"]),
                    entry_lamports=int(state["entry"]),
                    exit_lamports=int(state["exit"]),
                    realized_net_lamports=int(state["exit"]) - int(state["entry"]),
                    unclosed=True,
                )
            )
    frozen_trips = tuple(trips)
    closed_trips = [trip for trip in frozen_trips if not trip.unclosed]
    return RoundTripsResult(
        trips=frozen_trips,
        closed=len(closed_trips),
        unclosed_count=len(frozen_trips) - len(closed_trips),
        wins=sum(1 for trip in closed_trips if trip.realized_net_lamports > 0),
        losses=sum(1 for trip in closed_trips if trip.realized_net_lamports < 0),
        total_realized_net_lamports=sum(trip.realized_net_lamports for trip in closed_trips),
    )


def per_strategy_breakdown(
    result: RoundTripsResult,
) -> Mapping[str, int]:
    """Realized net lamports per strategy id; sums to the result total.

    The desk-view total is ``result.total_realized_net_lamports`` and the
    parts here sum to it exactly: integer equality, never rounding.
    """
    breakdown: dict[str, int] = {}
    for trip in result.trips:
        if trip.unclosed:
            continue
        breakdown[trip.strategy_id] = (
            breakdown.get(trip.strategy_id, 0) + trip.realized_net_lamports
        )
    return dict(sorted(breakdown.items()))
=======
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
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
