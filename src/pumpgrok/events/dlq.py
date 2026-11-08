"""DLQ list, replay, and purge against a caller-supplied sidecar handle."""

from __future__ import annotations

from pumpgrok.events.bus import EventBus
from pumpgrok.events.models import Event
from pumpgrok.events.store import EventStore


def list_rows(store: EventStore) -> list[dict[str, str]]:
    return store.list_dlq()


async def replay(store: EventStore, bus: EventBus, name: str) -> Event | None:
    event = store.take_dlq(name)
    if event is None:
        return None
    await bus.publish(event)
    await bus.shutdown()
    return event


def purge(store: EventStore, name: str) -> bool:
    return store.purge_dlq(name)
