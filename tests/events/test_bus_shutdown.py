"""shutdown persists pending. recover delivers each pending event once."""

from __future__ import annotations

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


async def _unused(_event: Event) -> None:
    return None
