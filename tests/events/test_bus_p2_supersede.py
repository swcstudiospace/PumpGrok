"""P2 retries release the key lock during backoff. A superseded retry goes to the DLQ."""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from pumpgrok.events.bus import EventBus
from pumpgrok.events.constants import BACKOFF_INITIAL_S, BACKOFF_JITTER_S, SHUTDOWN_TIMEOUT_S
from pumpgrok.events.errors import TransientEvent
from pumpgrok.events.models import Event, EventKind
from pumpgrok.events.store import EventStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng


def _tick(n: int) -> Event:
    return Event(
        kind=EventKind.curve_tick,
        entity_id="mint",
        payload={"n": n},
        occurred_at=f"t{n}",
    )


async def _settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


def _dlq_rows(path: Path) -> list[tuple[str, str]]:
    with closing(sqlite3.connect(path)) as db:
        rows = db.execute("SELECT event_id, reason FROM dlq ORDER BY event_id").fetchall()
    return [(str(row[0]), str(row[1])) for row in rows]


async def _supersede(
    sidecar: Path, clock: FixtureClock, dlq_calls: list[str]
) -> tuple[list[int], Event]:
    """Fail tick 1 once, then publish tick 2 while tick 1 sleeps in its backoff."""
    calls: list[int] = []

    async def handler(event: Event) -> None:
        n = int(event.payload["n"])
        calls.append(n)
        if n == 1 and calls.count(1) == 1:
            raise TransientEvent(index=1)

    bus = EventBus(
        clock=clock,
        handler=handler,
        dlq=lambda event: dlq_calls.append(event.event_id),
        store=EventStore(sidecar),
        rng=make_rng(11),
    )
    await bus.start()
    stale = _tick(1)
    await bus.publish(stale)
    await _settle()
    assert calls == [1]
    await bus.publish(_tick(2))
    await _settle()
    return calls, stale


async def test_newer_p2_value_is_delivered_while_stale_retry_sleeps(tmp_path: Path) -> None:
    clock = FixtureClock(0.0)
    dlq_calls: list[str] = []
    calls, _stale = await _supersede(tmp_path / "events.sqlite", clock, dlq_calls)

    # The newer value ran while the stale retry was still in its backoff sleep.
    assert calls == [1, 2]
    assert clock.now() == 0.0
    assert dlq_calls == []


async def test_superseded_stale_retry_is_sent_to_dlq_with_reason_transient(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    clock = FixtureClock(0.0)
    dlq_calls: list[str] = []
    calls, stale = await _supersede(sidecar, clock, dlq_calls)

    clock.advance_to(BACKOFF_INITIAL_S + BACKOFF_JITTER_S)
    await _settle()

    # The stale retry never ran the handler again. It was sent to the DLQ instead.
    assert calls == [1, 2]
    assert dlq_calls == [stale.event_id]
    assert _dlq_rows(sidecar) == [(stale.event_id, "transient")]


@pytest.mark.parametrize("dlq_failure", ["none", "backoff", "shutdown"])
async def test_superseded_p2_backoff_cannot_replay_after_shutdown(
    tmp_path: Path, dlq_failure: str
) -> None:
    sidecar = tmp_path / "events.sqlite"
    store = EventStore(sidecar)
    clock = FixtureClock(0.0)
    calls: list[int] = []
    dlq_calls: list[str] = []

    async def handler(event: Event) -> None:
        n = int(event.payload["n"])
        calls.append(n)
        if n == 1:
            raise TransientEvent(index=1)

    bus = EventBus(
        clock=clock,
        handler=handler,
        dlq=lambda event: dlq_calls.append(event.event_id),
        store=store,
        rng=make_rng(11),
    )
    stale = _tick(1)
    original = stale.model_dump(mode="json")
    await bus.start()
    await bus.publish(stale)
    retry_workers = list(bus._workers)
    await _settle()
    await bus.publish(_tick(2))
    await _settle()
    assert calls == [1, 2]
    assert clock.now() == 0.0

    if dlq_failure != "none":
        # The stale decision must survive a failed durable write as well as cancellation.
        with closing(sqlite3.connect(sidecar)) as db:
            db.execute("ALTER TABLE dlq RENAME TO dlq_hidden")
        if dlq_failure == "backoff":
            clock.advance_to(BACKOFF_INITIAL_S + BACKOFF_JITTER_S)
            results = await asyncio.gather(*retry_workers, return_exceptions=True)
            assert len(results) == 1
            assert isinstance(results[0], sqlite3.OperationalError)
        # A still-unavailable sidecar must fail shutdown, not snapshot a fresh stale retry.
        with pytest.raises(sqlite3.OperationalError):
            await bus.shutdown()
        results = await asyncio.gather(*retry_workers, return_exceptions=True)
        assert len(results) == 1
        assert isinstance(results[0], sqlite3.OperationalError)
        assert stale.event_id in bus._p2_active
        assert stale.event_id in bus._seen
        assert store.load_pending() == []
        with closing(sqlite3.connect(sidecar)) as db:
            db.execute("ALTER TABLE dlq_hidden RENAME TO dlq")

    await bus.shutdown()
    assert calls == [1, 2]
    if dlq_failure == "none":
        # Shutdown interrupted the backoff; it did not wait for its deadline.
        assert clock.now() == 0.0
        assert dlq_calls == [stale.event_id]
    assert store.list_dlq() == [{"event_id": stale.event_id, "reason": "transient"}]
    assert store.load_pending() == []
    assert stale.event_id not in bus._p2_active
    assert stale.event_id not in bus._seen
    assert not store.is_applied(stale.event_id)
    assert stale.model_dump(mode="json") == original
    store.close()

    replayed: list[str] = []

    async def recovered_handler(event: Event) -> None:
        replayed.append(event.event_id)

    reopened = EventStore(sidecar)
    recovered = EventBus(
        clock=FixtureClock(clock.now()),
        handler=recovered_handler,
        dlq=lambda _event: None,
        store=reopened,
    )
    await recovered.recover()
    await recovered.recover()
    assert replayed == []
    assert reopened.list_dlq() == [{"event_id": stale.event_id, "reason": "transient"}]
    # The original immutable event, not a mutated stale marker, is the DLQ body.
    parked = reopened.take_dlq(stale.event_id)
    assert parked is not None
    assert parked.model_dump(mode="json") == original
    await recovered.shutdown()
    reopened.close()


async def test_unsuperseded_p2_backoff_remains_pending_and_recovers_once(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    store = EventStore(sidecar)
    clock = FixtureClock(0.0)
    tick = _tick(1)
    calls: list[str] = []

    async def transient(event: Event) -> None:
        calls.append(event.event_id)
        raise TransientEvent(index=1)

    bus = EventBus(clock=clock, handler=transient, dlq=lambda _event: None, store=store)
    await bus.start()
    await bus.publish(tick)
    await _settle()
    assert calls == [tick.event_id]
    await bus.shutdown()
    assert clock.now() == 0.0
    assert [event.event_id for event in store.load_pending()] == [tick.event_id]
    assert store.list_dlq() == []
    store.close()

    delivered: list[str] = []

    async def handler(event: Event) -> None:
        delivered.append(event.event_id)

    reopened = EventStore(sidecar)
    recovered = EventBus(
        clock=FixtureClock(1.0), handler=handler, dlq=lambda _event: None, store=reopened
    )
    await recovered.recover()
    await recovered.recover()
    assert delivered == [tick.event_id]
    assert reopened.load_pending() == []
    assert reopened.list_dlq() == []
    assert not reopened.is_applied(tick.event_id)
    await recovered.shutdown()
    reopened.close()


async def test_stale_p2_dlq_notification_does_not_add_an_unbounded_shutdown_wait(
    tmp_path: Path,
) -> None:
    store = EventStore(tmp_path / "events.sqlite")
    clock = FixtureClock(0.0)
    entered = asyncio.Event()
    release = asyncio.Event()
    calls: list[int] = []

    async def handler(event: Event) -> None:
        n = int(event.payload["n"])
        calls.append(n)
        if n == 1:
            raise TransientEvent(index=1)

    async def dlq(_event: Event) -> None:
        entered.set()
        await release.wait()

    bus = EventBus(clock=clock, handler=handler, dlq=dlq, store=store)
    stale = _tick(1)
    await bus.start()
    await bus.publish(stale)
    await _settle()
    await bus.publish(_tick(2))
    await _settle()
    stopping = asyncio.create_task(bus.shutdown())
    await entered.wait()
    await _settle()
    assert not stopping.done()
    clock.advance_to(SHUTDOWN_TIMEOUT_S)
    await stopping
    assert calls == [1, 2]
    assert store.list_dlq() == [{"event_id": stale.event_id, "reason": "transient"}]
    assert store.load_pending() == []
    assert stale.event_id not in bus._p2_active
    assert stale.event_id not in bus._seen
    release.set()
    await _settle()
    store.close()
