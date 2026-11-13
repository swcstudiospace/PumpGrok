"""Bridge read-only market observations onto the existing event bus.

Curve observations are recorded durably first, then handed to the live price source,
then published as ``curve_tick``. Portal and trade facts publish as the existing
``token_created``, ``migration`` and ``trade`` kinds without a recorder: they carry no
reserves and never authorize a price.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.events.bus import EventBus
from pumpgrok.events.models import Event, EventKind, FrozenPayload
from pumpgrok.replay.live_recorder import LiveRecorder

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
