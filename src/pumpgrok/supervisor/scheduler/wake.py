"""Event wake matrix and event-mode timers (EVT-10). Owner-confirmed; do not edit casually.

Event mode runs a seat when a bus event on its row arrives, or when it is one of
``EVENT_TIMERS`` and that timer elapsed. Nothing else starts a seat in event mode.
Cadence mode does not read this module.
"""

from __future__ import annotations

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
