"""Read-only PumpPortal feed for token creation and migration, with bounded recovery."""

from __future__ import annotations

from pumpgrok.datafeed.bridge import ObservationBridge
from pumpgrok.datafeed.mintbook import MintBook
from pumpgrok.datafeed.readonly import ReadOnlyBoundary
from pumpgrok.datafeed.resync import FeedStats, FrameSource, GapLedger, RollingWindowLimiter
from pumpgrok.events.sources import SourceSupervisor
from pumpgrok.replay.clock import Clock

PORTAL_SUBSCRIPTIONS = ("subscribeNewToken", "subscribeMigration")


class PortalFeed:
    def __init__(
        self,
        *,
        boundary: ReadOnlyBoundary,
        frames: FrameSource,
        clock: Clock,
        supervisor: SourceSupervisor,
        mintbook: MintBook,
        bridge: ObservationBridge,
        limiter: RollingWindowLimiter,
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
