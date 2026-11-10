"""Temporary typed interface for the live observation price source."""

from pumpgrok.core.ids import Clock
from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.events.sources import SourceSupervisor
from pumpgrok.execution.paper_adapter.models import CurveSnapshot


class LivePriceSource:
    def __init__(self, *, clock: Clock, health: SourceSupervisor, max_age_s: float) -> None:
        pass

    def observe(self, observation: CurveObservation) -> None:
        pass

    async def curve(self, mint: str) -> CurveSnapshot | None:
        return None
