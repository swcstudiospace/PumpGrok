"""Bounded shutdown, EventBusClosed, recover-once, and the crash path.

Virtual time only. The shutdown bound fires when a test advances FixtureClock.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

import pytest

from pumpgrok.events.bus import EventBus
from pumpgrok.events.constants import SHUTDOWN_TIMEOUT_S
from pumpgrok.events.errors import EventBusClosed
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


def _mark(n: int) -> Event:
    return Event(
        kind=EventKind.mark,
        entity_id="mint",
        payload={"n": n},
        occurred_at=f"m{n}",
    )


async def _settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


async def _crash(bus: EventBus) -> None:
    """Stop the bus tasks as a process exit would. Nothing is saved, nothing is DLQ'd."""
    tasks = list(bus._workers)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


@contextmanager
def _db(path: Path) -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(path)) as db:
        yield db


def _count(path: Path, table: str) -> int:
    with _db(path) as db:
        row = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    assert row is not None
    return int(row[0])


def _no_dlq(_event: Event) -> None:
    return None


async def test_shutdown_persists_and_recover_delivers_once(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    first = _event("a")
    second = _event("b")
    parked = EventBus(
        clock=FixtureClock(0.0),
        handler=_unused,
        dlq=_no_dlq,
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
        dlq=_no_dlq,
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
        dlq=_no_dlq,
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
        dlq=_no_dlq,
        store=EventStore(sidecar),
    )
    await recovered.recover()
    assert replayed.event_id in delivered
    assert queued.event_id in delivered


async def test_shutdown_waits_for_handler_that_finishes_within_bound(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    event = _event("slow")
    started = asyncio.Event()
    gate = asyncio.Event()

    async def slow(_event: Event) -> None:
        started.set()
        await gate.wait()

    clock = FixtureClock(0.0)
    bus = EventBus(clock=clock, handler=slow, dlq=_no_dlq, store=EventStore(sidecar))
    await bus.start()
    await bus.publish(event)
    await started.wait()
    stopping = asyncio.create_task(bus.shutdown())
    await _settle()
    assert not stopping.done()
    gate.set()
    await stopping

    assert clock.now() == 0.0
    assert _count(sidecar, "applied") == 1
    assert _count(sidecar, "pending") == 0
    assert _count(sidecar, "dlq") == 0


async def test_shutdown_cancels_handler_past_bound_and_new_bus_recovers_once(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "events.sqlite"
    event = _event("stuck")
    started = asyncio.Event()
    never = asyncio.Event()

    async def stuck(_event: Event) -> None:
        started.set()
        await never.wait()

    clock = FixtureClock(0.0)
    bus = EventBus(clock=clock, handler=stuck, dlq=_no_dlq, store=EventStore(sidecar))
    await bus.start()
    await bus.publish(event)
    await started.wait()
    stopping = asyncio.create_task(bus.shutdown())
    await _settle()
    clock.advance_to(SHUTDOWN_TIMEOUT_S)
    await stopping

    # Cancellation is not a failure: no DLQ row, no applied row, the event stays pending.
    assert _count(sidecar, "dlq") == 0
    assert _count(sidecar, "applied") == 0
    assert _count(sidecar, "pending") == 1

    delivered: list[str] = []

    async def handler(item: Event) -> None:
        delivered.append(item.event_id)

    recovered = EventBus(
        clock=FixtureClock(SHUTDOWN_TIMEOUT_S),
        handler=handler,
        dlq=_no_dlq,
        store=EventStore(sidecar),
    )
    await recovered.recover()
    assert delivered == [event.event_id]
    await recovered.recover()
    assert delivered == [event.event_id]
    assert _count(sidecar, "applied") == 1
    assert _count(sidecar, "pending") == 0


async def test_shutdown_returns_at_its_bounds_when_handler_swallows_cancellation(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "events.sqlite"
    event = _event("stubborn")
    started = asyncio.Event()
    never = asyncio.Event()

    async def stubborn(_event: Event) -> None:
        started.set()
        while not never.is_set():
            try:
                await never.wait()
            except asyncio.CancelledError:
                continue

    clock = FixtureClock(0.0)
    bus = EventBus(clock=clock, handler=stubborn, dlq=_no_dlq, store=EventStore(sidecar))
    await bus.start()
    await bus.publish(event)
    await started.wait()
    stopping = asyncio.create_task(bus.shutdown())
    await _settle()
    clock.advance_to(SHUTDOWN_TIMEOUT_S)
    await _settle()
    clock.advance_to(2 * SHUTDOWN_TIMEOUT_S)
    await stopping

    # The call swallowed its cancellation and is still running. Shutdown returned at its
    # second bound. The event is pending: not applied and not in the DLQ.
    assert _count(sidecar, "pending") == 1
    assert _count(sidecar, "applied") == 0
    assert _count(sidecar, "dlq") == 0
    never.set()
    await _settle()


async def test_p2_in_flight_at_bound_and_queued_value_survive_restart(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    first = _tick(1)
    second = _tick(2)
    started = asyncio.Event()
    never = asyncio.Event()

    async def blocked(item: Event) -> None:
        if item.payload["n"] == 1:
            started.set()
            await never.wait()

    clock = FixtureClock(0.0)
    parked = EventBus(clock=clock, handler=blocked, dlq=_no_dlq, store=EventStore(sidecar))
    await parked.start()
    await parked.publish(first)
    await started.wait()
    await parked.publish(second)
    stopping = asyncio.create_task(parked.shutdown())
    await _settle()
    clock.advance_to(SHUTDOWN_TIMEOUT_S)
    await stopping

    assert _count(sidecar, "pending") == 2
    assert _count(sidecar, "applied") == 0
    assert _count(sidecar, "dlq") == 0

    delivered: list[str] = []

    async def handler(item: Event) -> None:
        delivered.append(item.event_id)

    recovered = EventBus(
        clock=FixtureClock(SHUTDOWN_TIMEOUT_S),
        handler=handler,
        dlq=_no_dlq,
        store=EventStore(sidecar),
    )
    await recovered.recover()
    assert delivered == [first.event_id, second.event_id]
    await recovered.recover()
    assert delivered == [first.event_id, second.event_id]


async def test_shutdown_cancels_debounce_and_mark_is_recovered_once(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    mark = _mark(1)
    parked_calls: list[int] = []

    async def parked_handler(item: Event) -> None:
        parked_calls.append(int(item.payload["n"]))

    parked = EventBus(
        clock=FixtureClock(0.0),
        handler=parked_handler,
        dlq=_no_dlq,
        store=EventStore(sidecar),
    )
    await parked.start()
    await parked.publish(mark)
    await _settle()
    # The debounce wait is cancelled, not waited out. No clock advance is needed.
    await parked.shutdown()

    assert parked_calls == []
    assert _count(sidecar, "pending") == 1
    assert _count(sidecar, "applied") == 0

    delivered: list[str] = []

    async def handler(item: Event) -> None:
        delivered.append(item.event_id)

    recovered = EventBus(
        clock=FixtureClock(1.0),
        handler=handler,
        dlq=_no_dlq,
        store=EventStore(sidecar),
    )
    await recovered.recover()
    assert delivered == [mark.event_id]
    await recovered.recover()
    assert delivered == [mark.event_id]
    assert _count(sidecar, "pending") == 0


async def test_publish_and_start_after_shutdown_raise_event_bus_closed(tmp_path: Path) -> None:
    bus = EventBus(
        clock=FixtureClock(0.0),
        handler=_unused,
        dlq=_no_dlq,
        store=EventStore(tmp_path / "events.sqlite"),
    )
    await bus.shutdown()
    with pytest.raises(EventBusClosed):
        await bus.publish(_event("late"))
    with pytest.raises(EventBusClosed):
        await bus.publish(_tick(1))
    with pytest.raises(EventBusClosed):
        await bus.start()
    await bus.shutdown()


async def test_crash_without_shutdown_runs_accepted_p0_once_on_new_bus(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    event = Event(
        kind=EventKind.kill_switch,
        entity_id="desk",
        payload={"reason": "daily_loss"},
        occurred_at="2026-01-01T10:00:00Z",
    )
    started = asyncio.Event()
    never = asyncio.Event()

    async def blocked(_event: Event) -> None:
        started.set()
        await never.wait()

    crashed = EventBus(
        clock=FixtureClock(0.0),
        handler=blocked,
        dlq=_no_dlq,
        store=EventStore(sidecar),
    )
    await crashed.start()
    await crashed.publish(event)
    await started.wait()
    await _crash(crashed)

    assert _count(sidecar, "pending") == 1
    assert _count(sidecar, "applied") == 0
    assert _count(sidecar, "dlq") == 0

    delivered: list[str] = []

    async def handler(item: Event) -> None:
        delivered.append(item.event_id)

    recovered = EventBus(
        clock=FixtureClock(1.0),
        handler=handler,
        dlq=_no_dlq,
        store=EventStore(sidecar),
    )
    await recovered.recover()
    assert delivered == [event.event_id]
    await recovered.recover()
    assert delivered == [event.event_id]


async def _unused(_event: Event) -> None:
    return None
