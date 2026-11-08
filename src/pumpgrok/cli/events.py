"""events dlq list, replay, and purge. Refuses when the section is off."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from pumpgrok.cli.codes import EXIT_CONFIG, EXIT_OK
from pumpgrok.cli.errors import UsageError, _say
from pumpgrok.config.settings import Settings
from pumpgrok.events.bus import EventBus
from pumpgrok.events.dlq import list_rows, purge, replay
from pumpgrok.events.models import Event
from pumpgrok.events.store import EventStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng


def events_verb(args: argparse.Namespace, settings: Settings) -> int:
    if not settings.events.enabled:
        _say(sys.stderr, "refused: events disabled")
        return EXIT_CONFIG
    command = getattr(args, "dlq_cmd", None)
    if getattr(args, "cmd", None) != "dlq" or command not in {"list", "replay", "purge"}:
        raise UsageError("events requires dlq list, replay, or purge")
    store = EventStore(settings.events.sidecar_path)
    try:
        if command == "list":
            _say(sys.stdout, json.dumps(list_rows(store)))
            return EXIT_OK
        name = getattr(args, "name", None)
        if not name:
            raise UsageError("events dlq row name is required")
        if command == "purge":
            if not purge(store, name):
                raise UsageError("unknown dlq row")
            _say(sys.stdout, json.dumps({"purged": name}))
            return EXIT_OK
        event = asyncio.run(_replay(settings, store, name))
    finally:
        store.close()
    _say(sys.stdout, json.dumps({"event_id": event.event_id}))
    return EXIT_OK


async def _replay(settings: Settings, store: EventStore, name: str) -> Event:
    bus = EventBus.from_settings(
        settings,
        clock=FixtureClock(0.0),
        handler=_noop,
        dlq=lambda _event: None,
        rng=make_rng(1),
    )
    try:
        event = await replay(store, bus, name)
    finally:
        if bus._store is not None:
            bus._store.close()
    if event is None:
        raise UsageError("unknown dlq row")
    return event


async def _noop(_event: Event) -> None:
    return None
