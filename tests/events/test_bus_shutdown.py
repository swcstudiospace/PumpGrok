"""shutdown persists pending. recover delivers each pending event once."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pumpgrok.events.bus import EventBus
from pumpgrok.events.models import Event, EventKind
from pumpgrok.events.store import EventStore
from pumpgrok.replay.clock import FixtureClock


def _event(occurred_at: str) -> Event:
    return Event(
        kind=EventKind.halt,
        entity_id="desk",
        payload={"n": occurred_at},
        occurred_at=occurred_at,
    )


def _tick(n: int) -> Event:
    return Event(
        kind=EventKind.curve_tick,
        entity_id="mint",
        payload={"n": n},
        occurred_at=f"t{n}",
    )


async def _crash(bus: EventBus) -> None:
    """Stop the bus tasks as a process exit would: a handler that never returns."""
    tasks = [*bus._tasks.values(), *bus._p2_tasks.values()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def test_shutdown_persists_and_recover_delivers_once(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    first = _event("a")
    second = _event("b")
    parked = EventBus(
        clock=FixtureClock(0.0),
        handler=_unused,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await parked.publish(first)
    await parked.publish(second)
    await parked.shutdown()

    delivered: list[str] = []

    async def handler(event: Event) -> None:
        delivered.append(event.event_id)

    recovered = EventBus(
        clock=FixtureClock(1.0),
        handler=handler,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await recovered.recover()
    assert delivered == [first.event_id, second.event_id]
    await recovered.recover()
    assert delivered == [first.event_id, second.event_id]


async def test_shutdown_keeps_replayed_pending_for_recover(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    replayed = Event(
        kind=EventKind.kill_switch,
        entity_id="desk",
        payload={"reason": "daily_loss"},
        occurred_at="2026-01-01T10:00:00Z",
    )
    store = EventStore(sidecar)
    store.write_dlq(replayed, reason="poison")
    assert store.move_dlq_to_pending(replayed.event_id) is not None
    queued = _event("queued")
    bus = EventBus(
        clock=FixtureClock(0.0),
        handler=_unused,
        dlq=lambda _event: None,
        store=store,
    )
    await bus.publish(queued)
    await bus.shutdown()
    store.close()

    delivered: list[str] = []

    async def handler(event: Event) -> None:
        delivered.append(event.event_id)

    recovered = EventBus(
        clock=FixtureClock(1.0),
        handler=handler,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await recovered.recover()
    assert replayed.event_id in delivered
    assert queued.event_id in delivered


async def test_inflight_lane_event_is_saved_by_shutdown_and_delivered_once_after_restart(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "events.sqlite"
    event = _event("inflight")
    started = asyncio.Event()
    never = asyncio.Event()

    async def blocked(_event: Event) -> None:
        started.set()
        await never.wait()

    parked = EventBus(
        clock=FixtureClock(0.0),
        handler=blocked,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await parked.start()
    await parked.publish(event)
    await started.wait()
    await parked.shutdown()
    await _crash(parked)

    delivered: list[str] = []

    async def handler(item: Event) -> None:
        delivered.append(item.event_id)

    recovered = EventBus(
        clock=FixtureClock(1.0),
        handler=handler,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await recovered.recover()
    assert delivered == [event.event_id]
    await recovered.recover()
    assert delivered == [event.event_id]


async def test_inflight_p2_event_is_saved_by_shutdown_and_both_values_survive_restart(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "events.sqlite"
    first = _tick(1)
    second = _tick(2)
    started = asyncio.Event()
    never = asyncio.Event()

    async def blocked(item: Event) -> None:
        if item.payload["n"] == 1:
            started.set()
            await never.wait()

    parked = EventBus(
        clock=FixtureClock(0.0),
        handler=blocked,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await parked.start()
    await parked.publish(first)
    await started.wait()
    await parked.publish(second)
    await parked.shutdown()
    await _crash(parked)

    delivered: list[str] = []

    async def handler(item: Event) -> None:
        delivered.append(item.event_id)

    recovered = EventBus(
        clock=FixtureClock(1.0),
        handler=handler,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await recovered.recover()
    assert delivered == [first.event_id, second.event_id]


async def _unused(_event: Event) -> None:
    return None
