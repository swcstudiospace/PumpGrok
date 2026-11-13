"""Real EventBus to seat dispatch in event mode (EVT-10).

Events go through the bus, its handler is the supervisor, and the seat cycles record what ran.
No wall-clock waits: the bus and the supervisor share one FixtureClock.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pumpgrok.events.bus import EventBus
from pumpgrok.events.constants import P2_DEBOUNCE_S
from pumpgrok.events.models import Event, EventKind
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.supervisor.scheduler import ROSTER, Supervisor
from pumpgrok.supervisor.scheduler.wake import wake_order
from pumpgrok.supervisor.seat_task import SeatContext

RISK = "bot-02-risk"
EXIT = "bot-06-exit"
JOURNAL = "bot-09-journal"


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))


def _recording_cycles(log: list[str]) -> dict[str, Any]:
    async def _record(ctx: SeatContext) -> dict[str, Any]:
        log.append(ctx.seat_id)
        return {"ok": True}

    return dict.fromkeys(ROSTER, _record)


def _event(kind: EventKind, entity_id: str, n: int) -> Event:
    return Event(
        kind=kind,
        entity_id=entity_id,
        payload={"n": n},
        occurred_at=f"2026-01-01T00:00:{n:02d}.000+00:00",
    )


async def _yield(rounds: int = 20) -> None:
    for _ in range(rounds):
        await asyncio.sleep(0)


async def _settle(done: Callable[[], bool]) -> None:
    for _ in range(500):
        if done():
            return
        await asyncio.sleep(0)
    raise AssertionError("event delivery did not settle")


async def test_each_bus_event_wakes_its_row_seats_once(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    log: list[str] = []
    dlq: list[Event] = []
    try:
        supervisor = Supervisor(
            store=store,
            clock=clock,
            rng=make_rng(7),
            cycles=_recording_cycles(log),
            wake_mode="event",
        )
        bus = EventBus(clock=clock, handler=supervisor.on_event, dlq=dlq.append)
        await bus.start()
        for n, kind in enumerate(EventKind, start=1):
            before = len(log)
            expected = wake_order(kind)
            await bus.publish(_event(kind, f"mint-{n}", n))
            # Mark is debounced on the clock: let its timer be scheduled, then fire it.
            await _yield()
            clock.advance_to(clock.now() + P2_DEBOUNCE_S)
            await _settle(lambda: len(log) - before >= len(expected))
            await _yield()
            assert log[before:] == list(expected), kind
        assert dlq == []
        await bus.shutdown()
    finally:
        store.close()


async def test_redelivered_event_wakes_its_seats_once(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    log: list[str] = []
    dlq: list[Event] = []
    try:
        supervisor = Supervisor(
            store=store,
            clock=clock,
            rng=make_rng(7),
            cycles=_recording_cycles(log),
            wake_mode="event",
        )
        bus = EventBus(clock=clock, handler=supervisor.on_event, dlq=dlq.append)
        await bus.start()
        event = _event(EventKind.trade, "mint-a", 1)
        await bus.publish(event)
        await _settle(lambda: len(log) >= len(wake_order(EventKind.trade)))
        await bus.publish(event)
        await _yield(50)
        assert log == list(wake_order(EventKind.trade))
        assert dlq == []
        await bus.shutdown()
    finally:
        store.close()


async def test_timers_run_once_after_bus_events_and_respect_event_starts(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    log: list[str] = []
    dlq: list[Event] = []
    try:
        supervisor = Supervisor(
            store=store,
            clock=clock,
            rng=make_rng(7),
            cycles=_recording_cycles(log),
            wake_mode="event",
        )
        bus = EventBus(clock=clock, handler=supervisor.on_event, dlq=dlq.append)
        await bus.start()
        await bus.publish(_event(EventKind.trade, "mint-a", 1))
        await _settle(lambda: len(log) == len(wake_order(EventKind.trade)))
        await _yield()

        # Trade already started EXIT and JOURNAL at t=0; only RISK has no timer start yet.
        clock.advance_to(5.0)
        outcomes = await supervisor.run_once()
        assert list(outcomes) == [RISK]
        assert log[len(wake_order(EventKind.trade)) :] == [RISK]

        # At t=15 EXIT's watchdog is due again, and RISK's 5 s staleness is due again.
        clock.advance_to(15.0)
        outcomes = await supervisor.tick_once()
        assert list(outcomes) == [RISK, EXIT]
        assert JOURNAL not in outcomes

        assert dlq == []
        await bus.shutdown()
    finally:
        store.close()
