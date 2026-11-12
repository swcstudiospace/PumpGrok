"""Read-only Solana logs feed for pump program trades, with bounded recovery."""

from __future__ import annotations

from pumpgrok.datafeed.bridge import ObservationBridge
from pumpgrok.datafeed.readonly import ReadOnlyBoundary
from pumpgrok.datafeed.resync import FeedStats, FrameSource, GapLedger, RollingWindowLimiter
from pumpgrok.datafeed.watchset import WatchSet
from pumpgrok.events.sources import SourceSupervisor
from pumpgrok.replay.clock import Clock

PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


class LogsFeed:
    def __init__(
        self,
        *,
        boundary: ReadOnlyBoundary,
        frames: FrameSource,
        clock: Clock,
        supervisor: SourceSupervisor,
        watch: WatchSet,
        bridge: ObservationBridge,
        limiter: RollingWindowLimiter,
        dedup_capacity: int = 4096,
    ) -> None:
        raise NotImplementedError

    @property
    def stats(self) -> FeedStats:
        raise NotImplementedError

    @property
    def gaps(self) -> GapLedger:
        raise NotImplementedError

    async def subscribe(self) -> None:
        raise NotImplementedError

    async def pump_once(self) -> None:
        raise NotImplementedError
