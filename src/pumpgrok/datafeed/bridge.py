"""Bridge datafeed events and read-only market observations onto the event bus.

Imports events models only: never the supervisor, never a network client.
The publisher is injected, so tests pass a recording fake.

Curve observations are recorded durably first, then handed to the live price
source, then published as ``curve_tick``. Portal and trade facts publish as the
existing ``token_created``, ``migration`` and ``trade`` kinds without a
recorder: they carry no reserves and never authorize a price.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Protocol

from pumpgrok.datafeed.events import (
    CurveObservation,
    CurveTick,
    DatafeedEvent,
    GapEvent,
    MarkMade,
    Migrated,
    TokenCreated,
    TradeSeen,
)
from pumpgrok.events.models import Event, EventKind, FrozenPayload
from pumpgrok.replay.clock import Clock

if TYPE_CHECKING:
    from pumpgrok.events.bus import Dlq, EventBus, Handler
    from pumpgrok.replay.live_recorder import LiveRecorder


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


MARKET_KINDS = frozenset({EventKind.token_created, EventKind.migration, EventKind.trade})


class PriceObserver(Protocol):
    def observe(self, observation: CurveObservation) -> None: ...


class ObservationBridge:
    def __init__(
        self,
        *,
        bus: EventBus,
        recorder: LiveRecorder,
        price: PriceObserver | None = None,
    ) -> None:
        self.bus = bus
        self.recorder = recorder
        self.price = price

    async def publish(self, observation: CurveObservation) -> None:
        observation.validate()
        event = Event(
            kind=EventKind.curve_tick,
            entity_id=observation.mint,
            payload=FrozenPayload(observation.replay_tick()),
            occurred_at=observation.ts_utc,
        )
        self.recorder.record(observation)
        if self.price is not None:
            self.price.observe(observation)
        await self.bus.publish(event)

    async def publish_market_event(
        self,
        *,
        kind: EventKind,
        mint: str,
        occurred_at: str,
        payload: Mapping[str, str | int | bool],
        lamports: int | None = None,
        token_units: int | None = None,
    ) -> None:
        """Publish a Portal or trade fact under an existing market kind.

        Units are exact integers; the event model refuses floats. Curve ticks are
        not a market kind and must go through :meth:`publish`.
        """
        if kind not in MARKET_KINDS:
            raise ValueError("event kind is not a market kind")
        event = Event(
            kind=kind,
            entity_id=mint,
            payload=FrozenPayload(dict(payload)),
            occurred_at=occurred_at,
            lamports=lamports,
            token_units=token_units,
        )
        await self.bus.publish(event)


def build_observation_bridge(
    *,
    clock: Clock,
    handler: Handler,
    dlq: Dlq,
    recorder: LiveRecorder,
    price: PriceObserver | None = None,
) -> ObservationBridge:
    """Build an :class:`ObservationBridge` over a new :class:`EventBus`.

    The bus is constructed here so composition roots that must not import the bus
    module can still obtain a bridge. The bridge behaves exactly as one built directly.
    """
    from pumpgrok.events.bus import EventBus  # noqa: PLC0415

    bus = EventBus(clock=clock, handler=handler, dlq=dlq)
    return ObservationBridge(bus=bus, recorder=recorder, price=price)
