"""events dlq list, replay, and purge. Refuses when the section is off."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from pumpgrok.cli.codes import EXIT_CONFIG, EXIT_OK
from pumpgrok.cli.errors import UsageError, _say
from pumpgrok.config.settings import Settings
from pumpgrok.events.dlq import list_rows, purge, replay
from pumpgrok.events.errors import SidecarRefusal
from pumpgrok.events.store import EventStore


def events_verb(args: argparse.Namespace, settings: Settings) -> int:
    if not settings.events.enabled:
        _say(sys.stderr, "refused: events disabled")
        return EXIT_CONFIG
    command = getattr(args, "dlq_cmd", None)
    if getattr(args, "cmd", None) != "dlq" or command not in {"list", "replay", "purge"}:
        raise UsageError("events requires dlq list, replay, or purge")
    try:
        store = EventStore(settings.events.sidecar_path)
    except (OSError, sqlite3.Error, SidecarRefusal) as exc:
        raise UsageError(f"sidecar unavailable: {exc}") from exc
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
        event = replay(store, name)
        if event is None:
            raise UsageError("unknown dlq row")
    finally:
        store.close()
    _say(sys.stdout, json.dumps({"event_id": event.event_id}))
    return EXIT_OK
