"""Per-entity FIFO and P0 isolation from a slow P1 handler."""

from __future__ import annotations

import asyncio

from pumpgrok.events.bus import EventBus
from pumpgrok.events.models import Event, EventKind
from pumpgrok.replay.clock import FixtureClock


def _event(kind: EventKind, entity_id: str, n: int, occurred_at: str) -> Event:
    return Event(
        kind=kind,
        entity_id=entity_id,
        payload={"n": n},
        occurred_at=occurred_at,
    )


async def test_same_entity_is_fifo_and_other_entities_do_not_block() -> None:
    order: list[tuple[str, int]] = []
    release_a = asyncio.Event()
    started_a = asyncio.Event()

    async def handler(event: Event) -> None:
        if event.entity_id == "A" and event.payload["n"] == 1:
            started_a.set()
            await release_a.wait()
        order.append((event.entity_id, int(event.payload["n"])))

    bus = EventBus(clock=FixtureClock(0.0), handler=handler, dlq=lambda _event: None)
    await bus.start()
    await bus.publish(_event(EventKind.trade, "A", 1, "t1"))
    await started_a.wait()
    await bus.publish(_event(EventKind.trade, "A", 2, "t2"))
    await bus.publish(_event(EventKind.trade, "B", 1, "t3"))
    for _ in range(20):
        if ("B", 1) in order:
            break
        await asyncio.sleep(0)
    assert ("B", 1) in order
    assert ("A", 2) not in order
    release_a.set()
    for _ in range(20):
        if ("A", 2) in order:
            break
        await asyncio.sleep(0)
    assert [item for item in order if item[0] == "A"] == [("A", 1), ("A", 2)]


async def test_slow_p1_does_not_delay_p0() -> None:
    order: list[str] = []
    release = asyncio.Event()
    p1_started = asyncio.Event()

    async def handler(event: Event) -> None:
        if event.kind is EventKind.trade:
            p1_started.set()
            await release.wait()
        order.append(event.kind.value)

    bus = EventBus(clock=FixtureClock(0.0), handler=handler, dlq=lambda _event: None)
    await bus.start()
    await bus.publish(
        Event(kind=EventKind.trade, entity_id="mint", payload={"n": 1}, occurred_at="t1")
    )
    await p1_started.wait()
    await bus.publish(
        Event(
            kind=EventKind.kill_switch,
            entity_id="desk",
            payload={"reason": "daily_loss"},
            occurred_at="t2",
        )
    )
    for _ in range(20):
        if "kill_switch" in order:
            break
        await asyncio.sleep(0)
    assert order == ["kill_switch"]
    release.set()
    for _ in range(20):
        if "trade" in order:
            break
        await asyncio.sleep(0)
    assert order == ["kill_switch", "trade"]


async def test_same_event_id_is_delivered_once() -> None:
    seen: list[str] = []

    async def handler(event: Event) -> None:
        seen.append(event.event_id)

    event = Event(
        kind=EventKind.halt,
        entity_id="desk",
        payload={"reason": "daily_loss"},
        occurred_at="t1",
    )
    bus = EventBus(clock=FixtureClock(0.0), handler=handler, dlq=lambda _event: None)
    await bus.publish(event)
    await bus.publish(event)
    await bus.start()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert seen == [event.event_id]
