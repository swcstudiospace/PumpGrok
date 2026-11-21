"""Bus bridge: datafeed events onto the Phase 12 bus via one EventKind catalog.

Imports events models only: never the supervisor, never a network client.
The publisher is injected, so tests pass a recording fake.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pumpgrok.datafeed.events import (
    CurveTick,
    DatafeedEvent,
    GapEvent,
    MarkMade,
    Migrated,
    TokenCreated,
    TradeSeen,
)
from pumpgrok.events.models import Event, EventKind, FrozenPayload

Publisher = Callable[[Event], None]


def _payload(record: DatafeedEvent) -> FrozenPayload:
    return FrozenPayload(dict(record.model_dump()))


def to_bus_event(record: DatafeedEvent) -> Event:
    """Map one datafeed event onto its single-catalog bus kind."""
    if isinstance(record, CurveTick):
        kind = EventKind.curve_tick
    elif isinstance(record, GapEvent):
        kind = EventKind.gap
    elif isinstance(record, TokenCreated):
        kind = EventKind.token_created
    elif isinstance(record, Migrated):
        kind = EventKind.migration
    elif isinstance(record, TradeSeen):
        kind = EventKind.trade
    elif isinstance(record, MarkMade):
        kind = EventKind.mark
    else:
        raise TypeError(f"unknown datafeed event: {type(record).__name__}")
    mint: str = getattr(record, "mint", "") or ""
    return Event(
        kind=kind,
        entity_id=mint,
        payload=_payload(record),
        occurred_at=record.ts_utc,
    )


def publish(record: DatafeedEvent, publisher: Publisher) -> Event:
    """Publish one datafeed event onto the injected publisher."""
    event = to_bus_event(record)
    publisher(event)
    return event
