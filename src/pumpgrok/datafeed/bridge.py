"""Bridge read-only curve observations onto the existing event bus."""

from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.events.bus import EventBus
from pumpgrok.events.models import Event, EventKind
from pumpgrok.replay.live_recorder import LiveRecorder


class ObservationBridge:
    def __init__(self, *, bus: EventBus, recorder: LiveRecorder) -> None:
        self.bus = bus
        self.recorder = recorder

    async def publish(self, observation: CurveObservation) -> None:
        observation.validate()
        event = Event(
            kind=EventKind.curve_tick,
            entity_id=observation.mint,
            payload=observation.replay_tick(),
            occurred_at=observation.ts_utc,
        )
        self.recorder.record(observation)
        await self.bus.publish(event)
