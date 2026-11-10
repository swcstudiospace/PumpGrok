# Temporary recorder interface for the Phase 13 tracer RED; not an implementation.

from pathlib import Path

from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.replay.clock import Clock


class LiveRecorder:
    def __init__(self, dataset_dir: Path, *, clock: Clock) -> None:
        self.dataset_dir = dataset_dir
        self.clock = clock

    def record(self, observation: CurveObservation) -> None:
        pass

    def seal(self) -> None:
        pass
