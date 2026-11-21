"""Event-mode wake dispatch (EVT-10, T-14-03-01/02).

Each EventKind maps to seat wakes via the closed SEAT_WAKES map; an unknown
kind wakes nothing. Only the allowed timer set may be configured; any other
timer fails closed at startup. The cadence path does not import this module.
"""

from __future__ import annotations

from dataclasses import dataclass

from pumpgrok.events.models import Event, EventKind
from pumpgrok.replay.clock import Clock

#: The complete set of timers permitted in event mode. `wake` itself is the
#: only timer; cadence ticks live on the cadence path, never here.
ALLOWED_TIMERS: frozenset[str] = frozenset({"wake"})


class UnknownTimerError(RuntimeError):
    """A timer outside the allowed set was configured."""


def assert_allowed_timers(timers: frozenset[str]) -> None:
    """Fail closed on any timer outside the allowed set."""
    unknown = set(timers) - set(ALLOWED_TIMERS)
    if unknown:
        raise UnknownTimerError(f"timers not allowed in event mode: {sorted(unknown)}")


#: Closed dispatch: EventKind -> seat wakes. P0 kinds wake the exit lane only
#: and never wait on P1 handlers (T-14-03-02).
SEAT_WAKES: dict[EventKind, tuple[str, ...]] = {
    EventKind.kill_switch: ("bot-06-exit",),
    EventKind.halt: ("bot-06-exit",),
    EventKind.exit_signal: ("bot-06-exit",),
    EventKind.risk_veto: ("bot-02-risk", "bot-06-exit"),
    EventKind.token_created: ("bot-01-scout", "bot-08-signal"),
    EventKind.migration: ("bot-01-scout", "bot-05-rug"),
    EventKind.trade: ("bot-03-whale", "bot-08-signal"),
    EventKind.position_opened: ("bot-05-rug", "bot-02-risk"),
    EventKind.position_closed: ("bot-09-journal",),
    EventKind.strategy_intent: ("bot-08-signal", "bot-04-sniper"),
    EventKind.curve_tick: ("bot-04-sniper",),
    EventKind.mark: ("bot-09-journal",),
    EventKind.gap: ("bot-02-risk",),
}


def wakes_for(kind: EventKind) -> tuple[str, ...]:
    """Seats woken by one event. Unknown kinds are not in the map's keys."""
    return SEAT_WAKES.get(kind, ())


@dataclass(frozen=True)
class Wake:
    seat: str
    event: Event


def dispatch(events: list[Event], *, clock: Clock) -> list[Wake]:
    """Consume bus events on the injected Clock and wake exactly those seats."""
    _ = clock.now()
    wakes: list[Wake] = []
    for event in events:
        for seat in wakes_for(event.kind):
            wakes.append(Wake(seat=seat, event=event))
    return wakes
