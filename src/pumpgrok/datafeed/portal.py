<<<<<<< HEAD
"""PumpPortal free-method feed (R45): new-token and migration frames only.

No trade-stream key, no wallet, no signing import. Reconnect (including
TIMEOUT) goes through the SourceSupervisor; an interval with no frames
becomes a gap event; duplicate signatures across a reconnect are deduped.
Timings through the injected Clock. Transport-agnostic: the caller feeds
frames in.
=======
"""Read-only PumpPortal feed for token creation and migration, with bounded recovery.

Only the two allowlisted subscriptions are sent, through the read-only boundary. Frame
shapes are the assumed PumpPortal ``txType`` values ``create`` and ``migrate``; any other
or incomplete frame is counted as malformed and never guessed. Creation admits the mint
to the watch set; a full set counts the overflow and publishes nothing. Migration of an
unwatched mint is counted, not published.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

<<<<<<< HEAD
from collections.abc import Callable
from typing import Any

from pumpgrok.datafeed.bridge import publish
from pumpgrok.datafeed.events import GapEvent, Migrated, TokenCreated
from pumpgrok.datafeed.readonly import guarded_call
from pumpgrok.events.models import Event
from pumpgrok.replay.clock import FixtureClock, WallClock, format_ts_utc

EventSink = Callable[[Event], None]
RecordSink = Callable[[Any], None]


class RateLimiter:
    """One shared bucket: at most capacity acquires per window_s. Shed, never burst."""

    def __init__(self, clock: FixtureClock | WallClock, capacity: int = 30, window_s: float = 10.0):
        if capacity < 1:
            raise ValueError("limiter capacity must be at least 1")
        self._clock = clock
        self._capacity = capacity
        self._window_s = window_s
        self._window_start: float | None = None
        self._count = 0
        self._shed = 0

    @property
    def shed(self) -> int:
        return self._shed

    def _roll(self) -> None:
        now = self._clock.now()
        if self._window_start is None or now - self._window_start >= self._window_s:
            self._window_start = now
            self._count = 0

    def try_acquire(self) -> bool:
        self._roll()
        if self._count >= self._capacity:
            self._shed += 1
            return False
        self._count += 1
        return True


class PortalFeed:
    """PumpPortal create/migration frames with supervisor reconnect semantics."""

    def __init__(
        self,
        clock: FixtureClock | WallClock,
        limiter: RateLimiter,
        supervisor: Any,
        on_record: RecordSink,
        on_event: EventSink,
    ) -> None:
        self._clock = clock
        self._limiter = limiter
        self._supervisor = supervisor
        self._on_record = on_record
        self._on_event = on_event
        self._seen_signatures: set[str] = set()
        self._last_frame_at: float | None = None
        self.unknown_frames = 0

    def _emit(self, record: Any) -> None:
        self._on_record(record)
        publish(record, self._on_event)

    def _note_frame(self) -> None:
        now = self._clock.now()
        self._last_frame_at = now
        self._supervisor.note_frame(now)

    def handle_frame(self, frame: dict[str, Any]) -> bool:
        """Handle one inbound frame; True when it produced an event.

        Malformed frames count as unknown and never produce trades.
        """
        method = str(frame.get("method", ""))
        signature = str(frame.get("signature", ""))
        if signature:
            if signature in self._seen_signatures:
                return False
            self._seen_signatures.add(signature)
        builder = {"subscribeNewToken": TokenCreated, "subscribeMigration": Migrated}.get(method)
        if builder is None:
            self.unknown_frames += 1
            return False
        if not self._limiter.try_acquire():
            return False
        guarded_call(method, lambda: None)
        mint = str(frame.get("mint", ""))
        if not mint:
            self.unknown_frames += 1
            return False
        self._note_frame()
        self._emit(builder(mint=mint, ts_utc=format_ts_utc(self._clock.now())))
        return True

    def handle_timeout(self) -> GapEvent:
        """TIMEOUT reconnect: supervisor backoff; the silent interval is a gap."""
        now = self._clock.now()
        start = self._last_frame_at if self._last_frame_at is not None else now
        self._supervisor.note_failure()
        gap = GapEvent(
            mint=None,
            ts_utc=format_ts_utc(now),
            reason="timeout",
            from_ts_utc=format_ts_utc(start),
            to_ts_utc=format_ts_utc(now),
        )
        self._emit(gap)
        return gap
=======
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
        self._gaps = GapLedger(clock, sink=bridge.recorder.record_gap)
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
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
