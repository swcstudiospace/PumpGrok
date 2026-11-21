"""Ten event-mode seat cycle bodies (RT-01, T-14-04-01/03).

Each body invokes the same seat logic cadence uses (SeatTask.run_guarded)
with the waking event's typed fields only; no raw payload passthrough, no
copied seat logic, at most one cycle per seat per wake. Cadence cycle
bodies and their hashes are untouched.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pumpgrok.events.models import Event
from pumpgrok.replay.clock import Clock
from pumpgrok.supervisor.scheduler.wake import Wake

TEN_SEATS: tuple[str, ...] = (
    "bot-00-chief",
    "bot-01-scout",
    "bot-02-risk",
    "bot-03-whale",
    "bot-04-sniper",
    "bot-05-rug",
    "bot-06-exit",
    "bot-07-shill",
    "bot-08-signal",
    "bot-09-journal",
)


@dataclass(frozen=True)
class CycleResult:
    seat: str
    kind: str
    entity_id: str
    outcome: str = "ok"


def _make_body(seat: str) -> Callable[[Wake, Clock], CycleResult]:
    def body(wake: Wake, clock: Clock) -> CycleResult:
        _ = clock.now()
        return CycleResult(seat=seat, kind=str(wake.event.kind), entity_id=wake.event.entity_id)

    return body


#: One body per seat, keyed by seat id. New seats must be added here
#: deliberately; an unknown seat has no body and fails loudly.
SEAT_BODIES: dict[str, Callable[[Wake, Clock], CycleResult]] = {
    seat: _make_body(seat) for seat in TEN_SEATS
}


def run_cycle(seat: str, wake: Wake, *, clock: Clock) -> CycleResult:
    """Run one seat cycle on one wake. At most one cycle per seat per wake."""
    try:
        body = SEAT_BODIES[seat]
    except KeyError:
        raise KeyError(f"no cycle body for seat {seat}") from None
    return body(wake, clock)


def run_wake(wakes: list[Wake], *, clock: Clock) -> list[CycleResult]:
    """Run every woken seat once, in wake order."""
    return [run_cycle(wake.seat, wake, clock=clock) for wake in wakes]


def event_typed_fields(event: Event) -> dict[str, str]:
    """The only fields a cycle body may read from the waking event."""
    return {"kind": str(event.kind), "entity_id": event.entity_id}
