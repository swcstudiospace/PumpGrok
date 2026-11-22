"""DeterministicBus reuses the Phase 12 drain; fixture_compat is exact."""

import random

import pytest

from pumpgrok.events.drain import drain
from pumpgrok.events.models import Event, EventKind
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.scheduler.event_cycles_aux import DeterministicBus


def _event(kind: EventKind, entity: str = "mint-a") -> Event:
    return Event(
        kind=kind,
        entity_id=entity,
        payload={"n": 1},
        occurred_at="2026-01-01T00:00:00.000000Z",
    )


def test_bus_matches_drain_bytes() -> None:
    events = [_event(EventKind.curve_tick), _event(EventKind.trade, "mint-b")]
    bus = DeterministicBus(clock=FixtureClock(0.0), rng=random.Random(20260101))
    delivered = bus.deliver(events)
    expected = drain(events, FixtureClock(0.0), random.Random(20260101))
    assert bytes(delivered) == bytes(expected)
    assert delivered.pending == expected.pending


def test_bus_requires_fixture_compat() -> None:
    bus = DeterministicBus(clock=FixtureClock(0.0), rng=random.Random(1))
    with pytest.raises(ValueError):
        bus.deliver([_event(EventKind.mark)], fixture_compat=False)
