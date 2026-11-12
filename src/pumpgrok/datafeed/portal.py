"""Read-only PumpPortal feed for token creation and migration, with bounded recovery.

Only the two allowlisted subscriptions are sent, through the read-only boundary. Frame
shapes are the assumed PumpPortal ``txType`` values ``create`` and ``migrate``; any other
or incomplete frame is counted as malformed and never guessed. Creation admits the mint
to the watch set; a full set counts the overflow and publishes nothing. Migration of an
unwatched mint is counted, not published.
"""

from __future__ import annotations

from pumpgrok.datafeed.bridge import ObservationBridge
from pumpgrok.datafeed.mintbook import STAGE_MIGRATED, MintBook
from pumpgrok.datafeed.readonly import ReadOnlyBoundary
from pumpgrok.datafeed.resync import (
    FeedStats,
    FrameSource,
    GapLedger,
    Recovery,
    RollingWindowLimiter,
)
from pumpgrok.events.models import EventKind
from pumpgrok.events.sources import SourceSupervisor
from pumpgrok.replay.clock import Clock

PORTAL_SUBSCRIPTIONS = ("subscribeNewToken", "subscribeMigration")


def _text(frame: dict[str, object], key: str) -> str | None:
    value = frame.get(key)
    return value if isinstance(value, str) and value.strip() else None


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
        self._boundary = boundary
        self._clock = clock
        self._mintbook = mintbook
        self._bridge = bridge
        self._limiter = limiter
        self._stats = FeedStats()
        self._gaps = GapLedger(clock)
        self._recovery = Recovery(
            clock=clock,
            supervisor=supervisor,
            frames=frames,
            gaps=self._gaps,
            subscribe=self.subscribe,
            held=lambda: mintbook.held,
        )

    @property
    def stats(self) -> FeedStats:
        return self._stats

    @property
    def gaps(self) -> GapLedger:
        return self._gaps

    async def subscribe(self) -> None:
        for method in PORTAL_SUBSCRIPTIONS:
            await self._limiter.acquire()
            await self._boundary.portal(method)

    async def pump_once(self) -> None:
        frame = await self._recovery.receive()
        if frame is None:
            return
        self._stats.received += 1
        await self._handle(frame)

    async def _handle(self, frame: object) -> None:
        if not isinstance(frame, dict):
            self._stats.malformed += 1
            return
        tx_type = frame.get("txType")
        mint = _text(frame, "mint")
        signature = _text(frame, "signature")
        if mint is None or signature is None:
            self._stats.malformed += 1
            return
        if tx_type == "create":
            await self._create(frame, mint, signature)
        elif tx_type == "migrate":
            await self._migrate(frame, mint, signature)
        else:
            self._stats.malformed += 1

    async def _create(self, frame: dict[str, object], mint: str, signature: str) -> None:
        name = _text(frame, "name")
        symbol = _text(frame, "symbol")
        if name is None or symbol is None:
            self._stats.malformed += 1
            return
        if self._mintbook.record(mint) is not None:
            self._stats.duplicate += 1
            return
        occurred_at = self._clock.utc_iso()
        if not self._mintbook.admit_created(mint, occurred_at):
            self._stats.unwatched += 1
            return
        await self._bridge.publish_market_event(
            kind=EventKind.token_created,
            mint=mint,
            occurred_at=occurred_at,
            payload={"signature": signature, "name": name, "symbol": symbol},
        )
        self._stats.applied += 1

    async def _migrate(self, frame: dict[str, object], mint: str, signature: str) -> None:
        pool = _text(frame, "pool")
        if pool is None:
            self._stats.malformed += 1
            return
        existing = self._mintbook.record(mint)
        if existing is not None and existing.stage == STAGE_MIGRATED:
            self._stats.duplicate += 1
            return
        occurred_at = self._clock.utc_iso()
        if not self._mintbook.mark_migrated(mint, occurred_at):
            self._stats.unwatched += 1
            return
        await self._bridge.publish_market_event(
            kind=EventKind.migration,
            mint=mint,
            occurred_at=occurred_at,
            payload={"signature": signature, "pool": pool},
        )
        self._stats.applied += 1
