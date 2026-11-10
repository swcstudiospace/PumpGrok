# Temporary bridge interface for the Phase 13 tracer RED; not an implementation.

from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.events.bus import EventBus
from pumpgrok.replay.live_recorder import LiveRecorder


class ObservationBridge:
    def __init__(self, *, bus: EventBus, recorder: LiveRecorder) -> None:
        self.bus = bus
        self.recorder = recorder

    async def publish(self, observation: CurveObservation) -> None:
        pass
