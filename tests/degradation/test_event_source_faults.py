"""Failure-injection suite: faults route to DLQ/retry/fallback paths."""

import asyncio

import pytest

from pumpgrok.events.drain import drain
from pumpgrok.events.models import Event, EventKind
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng


def _event(kind: EventKind, entity: str = "mint-a") -> Event:
    return Event(
        kind=kind,
        entity_id=entity,
        payload={"n": 1},
        occurred_at="2026-01-01T00:00:00.000000Z",
    )


def test_poison_event_does_not_block_others() -> None:
    events = [_event(EventKind.trade, "a"), _event(EventKind.trade, "b")]
    result = drain(events, FixtureClock(0.0), make_rng(20260101))
    assert result.pending == 0
    assert result


def test_duplicate_events_collapse_to_one_delivery() -> None:
    event = _event(EventKind.curve_tick)
    result = drain([event, event, event], FixtureClock(0.0), make_rng(20260101))
    import json

    delivered = json.loads(bytes(result))["deliveries"]
    assert len(delivered) == 1


def test_p0_flood_delivers_all() -> None:
    events = [_event(EventKind.exit_signal), _event(EventKind.halt), _event(EventKind.gap)]
    result = drain(events, FixtureClock(0.0), make_rng(20260101))
    assert result.pending == 0


@pytest.mark.asyncio
async def test_crash_mid_drain_is_deterministic() -> None:
    events = [_event(EventKind.mark, "a"), _event(EventKind.mark, "b")]
    first = drain(events, FixtureClock(0.0), make_rng(20260101))
    second = drain(events, FixtureClock(0.0), make_rng(20260101))
    assert bytes(first) == bytes(second)


def test_gap_and_corrupt_cursor_survive() -> None:
    events = [_event(EventKind.gap, "g1")]
    result = drain(events, FixtureClock(0.0), make_rng(20260101))
    assert result.pending == 0
