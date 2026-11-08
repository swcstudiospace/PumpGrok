"""P0 unbounded, P1 overflow to a sink, P2 coalesce."""

from __future__ import annotations

import asyncio

from pumpgrok.events.bus import EventBus
from pumpgrok.events.constants import P1_LANE_CAP, P2_DEBOUNCE_S
from pumpgrok.events.models import Event, EventKind
from pumpgrok.replay.clock import FixtureClock


def _p1(index: int) -> Event:
    return Event(
        kind=EventKind.trade,
        entity_id=f"mint-{index}",
        payload={"n": index},
        occurred_at=f"t{index}",
    )


async def test_p1_overflow_goes_to_dlq_and_p0_is_not_capped() -> None:
    dlq: list[Event] = []
    bus = EventBus(clock=FixtureClock(0.0), handler=_noop, dlq=dlq.append)
    for index in range(P1_LANE_CAP + 1):
        await bus.publish(_p1(index))
    assert len(dlq) == 1
    assert dlq[0].payload["n"] == P1_LANE_CAP
    assert bus.queued(1) == P1_LANE_CAP
    for index in range(P1_LANE_CAP + 5):
        await bus.publish(
            Event(
                kind=EventKind.halt,
                entity_id="desk",
                payload={"reason": "daily_loss", "n": index},
                occurred_at=f"p0-{index}",
            )
        )
    assert bus.queued(0) == P1_LANE_CAP + 5
    assert len(dlq) == 1


async def test_curve_tick_keeps_one_latest_pending_event() -> None:
    delivered: list[int] = []

    async def handler(event: Event) -> None:
        delivered.append(int(event.payload["n"]))

    bus = EventBus(clock=FixtureClock(0.0), handler=handler, dlq=lambda _event: None)
    first = Event(
        kind=EventKind.curve_tick,
        entity_id="mint",
        payload={"n": 1},
        occurred_at="t1",
    )
    second = Event(
        kind=EventKind.curve_tick,
        entity_id="mint",
        payload={"n": 2},
        occurred_at="t2",
    )
    await bus.publish(first)
    await bus.publish(second)
    assert bus.pending_p2(EventKind.curve_tick, "mint") == second
    await bus.start()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert delivered == [2]


async def test_mark_waits_debounce_then_delivers_latest() -> None:
    clock = FixtureClock(0.0)
    delivered: list[int] = []

    async def handler(event: Event) -> None:
        delivered.append(int(event.payload["n"]))

    bus = EventBus(clock=clock, handler=handler, dlq=lambda _event: None)
    await bus.start()
    await bus.publish(
        Event(kind=EventKind.mark, entity_id="mint", payload={"n": 1}, occurred_at="t1")
    )
    await bus.publish(
        Event(kind=EventKind.mark, entity_id="mint", payload={"n": 2}, occurred_at="t2")
    )
    await asyncio.sleep(0)
    assert bus.pending_p2(EventKind.mark, "mint") is not None
    assert int(bus.pending_p2(EventKind.mark, "mint").payload["n"]) == 2  # type: ignore[union-attr]
    clock.advance_to(P2_DEBOUNCE_S - 0.1)
    await asyncio.sleep(0)
    assert delivered == []
    clock.advance_to(P2_DEBOUNCE_S)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert delivered == [2]


async def _noop(_event: Event) -> None:
    return None
