<<<<<<< HEAD
"""Event-mode wake dispatch (EVT-10, T-14-03-01/02).

Each EventKind maps to seat wakes via the closed SEAT_WAKES map; an unknown
kind wakes nothing. Only the allowed timer set may be configured; any other
timer fails closed at startup. The cadence path does not import this module.
=======
"""Event wake matrix and event-mode timers (EVT-10). Owner-confirmed; do not edit casually.

Event mode runs a seat when a bus event on its row arrives, or when it is one of
``EVENT_TIMERS`` and that timer elapsed. Nothing else starts a seat in event mode.
Cadence mode does not read this module.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

<<<<<<< HEAD
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
=======
from collections.abc import Mapping
from types import MappingProxyType

from pumpgrok.core.manifests import EXPECTED_SEAT_IDS
from pumpgrok.events.models import EventKind

_CHIEF = "bot-00-chief"
_SCOUT = "bot-01-scout"
_RISK = "bot-02-risk"
_WHALE = "bot-03-whale"
_SNIPER = "bot-04-sniper"
_RUG = "bot-05-rug"
_EXIT = "bot-06-exit"
_SIGNAL = "bot-08-signal"
_JOURNAL = "bot-09-journal"

#: Seats woken by each bus event kind. Rows are listed in roster order.
SEAT_WAKES: Mapping[EventKind, tuple[str, ...]] = MappingProxyType(
    {
        EventKind.kill_switch: (_CHIEF, _RISK, _SNIPER, _EXIT, _SIGNAL),
        EventKind.halt: (_CHIEF, _RISK, _SNIPER, _EXIT, _SIGNAL),
        EventKind.exit_signal: (_RISK, _EXIT),
        EventKind.risk_veto: (_CHIEF, _RISK, _SNIPER),
        EventKind.token_created: (_SCOUT, _WHALE, _SIGNAL),
        EventKind.migration: (_SCOUT, _WHALE, _SIGNAL),
        EventKind.strategy_intent: (_RISK, _SNIPER),
        EventKind.curve_tick: (_RISK, _RUG, _EXIT),
        EventKind.mark: (_RISK, _RUG, _EXIT),
        EventKind.trade: (_CHIEF, _EXIT, _JOURNAL),
        EventKind.position_opened: (_CHIEF, _EXIT, _JOURNAL),
        EventKind.position_closed: (_CHIEF, _EXIT, _JOURNAL),
    }
)

#: Seats whose event-mode body is the trading and safety cycle in ``event_cycles`` (14-04 slice A).
EVENT_CYCLE_SEATS: frozenset[str] = frozenset({_CHIEF, _SCOUT, _RISK, _SNIPER, _RUG, _EXIT})

#: Seats whose event-mode body is the auxiliary cycle in ``event_cycles_aux`` (14-04 slice B).
#: Shill has no row in ``SEAT_WAKES``, so no event runs it and it keeps its replay body.
AUX_EVENT_CYCLE_SEATS: frozenset[str] = frozenset({_WHALE, _SIGNAL, _JOURNAL})

#: The only seats that may start on a timer in event mode, with their period in seconds.
#: 02-risk: 5 s staleness. 06-exit: 15 s watchdog. 09-journal: 300 s flush.
EVENT_TIMERS: Mapping[str, float] = MappingProxyType(
    {
        _RISK: 5.0,
        _EXIT: 15.0,
        _JOURNAL: 300.0,
    }
)

_ROSTER_INDEX: Mapping[str, int] = MappingProxyType(
    {seat: index for index, seat in enumerate(EXPECTED_SEAT_IDS)}
)

_ORDERED: Mapping[EventKind, tuple[str, ...]] = MappingProxyType(
    {
        kind: tuple(sorted(seats, key=_ROSTER_INDEX.__getitem__))
        for kind, seats in SEAT_WAKES.items()
    }
)


def wake_order(kind: EventKind) -> tuple[str, ...]:
    """Seats one event of ``kind`` wakes, each once, in roster order."""
    return _ORDERED[kind]
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
