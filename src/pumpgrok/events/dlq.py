"""DLQ list, replay, and purge against a caller-supplied sidecar handle."""

from __future__ import annotations

from pumpgrok.events.models import Event
from pumpgrok.events.store import EventStore


def list_rows(store: EventStore) -> list[dict[str, str]]:
    return store.list_dlq()


def replay(store: EventStore, name: str) -> Event | None:
    """Park the named DLQ row on pending for the next recover(). No bus, no clock."""
    return store.move_dlq_to_pending(name)


def purge(store: EventStore, name: str) -> bool:
    return store.purge_dlq(name)
