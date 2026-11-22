"""Fill grouping into round trips (BT-09; CONTEXT D-02).

Each fill is a signed cash movement on one mint key: a "buy" spends
lamports (entry), a "sell" receives lamports (exit). Fills group by key
in input order; consecutive buys before the first sell accumulate into
one open trip, partial sells fold into the same open trip, and a sell
closes it. A trip left open at the end is flagged ``unclosed`` and its
open entry basis is not counted as realized. Money stays integer
lamports throughout.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

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


@dataclass(frozen=True)
class RoundTrip:
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
        return sum(
            trip.realized_net_lamports for trip in self.trips if not trip.unclosed
        )


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
        total_realized_net_lamports=sum(
            trip.realized_net_lamports for trip in closed_trips
        ),
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
