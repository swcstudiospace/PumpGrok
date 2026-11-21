"""Fake feed harness: records frames and bus events without transport."""

from __future__ import annotations

from typing import Any

from pumpgrok.events.models import Event


class FakeFeed:
    """Recording fake for portal/logs sinks."""

    def __init__(self) -> None:
        self.records: list[Any] = []
        self.events: list[Event] = []

    def on_record(self, record: Any) -> None:
        self.records.append(record)

    def on_event(self, event: Event) -> None:
        self.events.append(event)
