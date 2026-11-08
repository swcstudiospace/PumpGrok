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


async def _unused(_event: Event) -> None:
    return None
