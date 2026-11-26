<<<<<<< HEAD
"""logsSubscribe trade feed (R46): bounded follow-ups through one limiter.

Trade events come from ``logsSubscribe`` on bonding-curve accounts; each
trade signature may take a bounded ``getTransaction`` follow-up through the
shared limiter. Malformed frames raise into the error path and count as
unknown; ``extra="forbid"`` models reject unexpected fields.
=======
"""Read-only Solana logs feed for pump program trades, with bounded recovery.

One ``logsSubscribe`` filter mentions the pump program. A notification's ``Program data:``
lines are attributed to the pump program by the invoke stack, so a payload emitted by
another program in the same transaction is never decoded as a pump event. Event identity
is ``(signature, log position)``, which keeps distinct events in one transaction apart and
collapses a repeated notification. Failed transactions are ignored. ``getTransaction`` is
read only when a notification's logs were truncated by the node.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

<<<<<<< HEAD
import base64
from collections.abc import Callable
from typing import Any

from pumpgrok.datafeed.bridge import publish
from pumpgrok.datafeed.events import TradeSeen
from pumpgrok.datafeed.portal import RateLimiter
from pumpgrok.datafeed.readonly import guarded_call
from pumpgrok.events.models import Event
from pumpgrok.replay.clock import FixtureClock, WallClock, format_ts_utc
from pumpgrok.tools.onchain.pump_events import EventDecodeError, decode_program_data

EventSink = Callable[[Event], None]
RecordSink = Callable[[Any], None]


class LogsFeed:
    """logsSubscribe frames into TradeSeen events, deduped by signature."""

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
        self._seen: set[str] = set()
        self.unknown_frames = 0
        self.follow_ups = 0

    def follow_up(self, signature: str) -> bool:
        """Bounded getTransaction follow-up through the shared limiter."""
        if not self._limiter.try_acquire():
            return False
        guarded_call("getTransaction", lambda: None)
        self.follow_ups += 1
        return True

    def handle_notification(self, notification: dict[str, Any]) -> bool:
        """Decode one logsSubscribe notification; True when it made an event."""
        guarded_call("logsSubscribe", lambda: None)
        value = notification.get("value", {})
        signature = ""
        entries: list[str] = []
        if isinstance(value, dict):
            signature = str(value.get("signature", ""))
            logs = value.get("logs", [])
            if isinstance(logs, list):
                entries = [str(item) for item in logs]
        if signature:
            if signature in self._seen:
                return False
            self._seen.add(signature)
        for entry in entries:
            if "Program data:" not in entry:
                continue
            try:
                encoded = entry.split("Program data: ", 1)[1].strip()
                raw = base64.b64decode(encoded, validate=True)
                event = decode_program_data(encoded)
                del raw
            except (EventDecodeError, ValueError) as exc:
                if isinstance(exc, EventDecodeError):
                    self.unknown_frames += 1
                    continue
                self.unknown_frames += 1
                continue
            mint = getattr(event, "mint", "")
            if not mint:
                self.unknown_frames += 1
                continue
            record = TradeSeen(
                mint=mint,
                ts_utc=format_ts_utc(self._clock.now()),
                signature=signature,
                sol_amount_lamports=int(getattr(event, "sol_amount", 0)),
                token_amount_units=int(getattr(event, "token_amount", 0)),
            )
            self._on_record(record)
            publish(record, self._on_event)
            self._supervisor.note_frame()
            return True
        self.unknown_frames += 1
        return False
=======
import re
from collections.abc import Sequence
from typing import TypeGuard

from pumpgrok.datafeed.bridge import ObservationBridge
from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.datafeed.readonly import ReadOnlyBoundary
from pumpgrok.datafeed.resync import (
    TRANSPORT_FAILURES,
    DedupWindow,
    FeedStats,
    FrameSource,
    GapLedger,
    Recovery,
    RollingWindowLimiter,
)
from pumpgrok.datafeed.watchset import WatchSet
from pumpgrok.events.models import EventKind
from pumpgrok.events.sources import SourceSupervisor
from pumpgrok.replay.clock import Clock
from pumpgrok.tools.onchain.pump_events import (
    EventDecodeError,
    PostCompleteBuyEvent,
    TradeEvent,
    decode_program_data,
)

PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
_DATA_PREFIX = "Program data: "
_TRUNCATED = "Log truncated"
_INVOKE = re.compile(r"Program (\S+) invoke \[\d+\]")
_RESULT = re.compile(r"Program (\S+) (?:success|failed.*)")


def _is_list_of_str(value: object) -> TypeGuard[list[str]]:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _notification_value(frame: object) -> tuple[str, object, list[str]] | None:
    """Extract (signature, err, logs) from a logsNotification frame, or None if malformed."""
    if not isinstance(frame, dict) or frame.get("method") != "logsNotification":
        return None
    params = frame.get("params")
    result = params.get("result") if isinstance(params, dict) else None
    value = result.get("value") if isinstance(result, dict) else None
    if not isinstance(value, dict):
        return None
    signature = value.get("signature")
    logs = value.get("logs")
    if not isinstance(signature, str) or not signature or not _is_list_of_str(logs):
        return None
    return signature, value.get("err"), list(logs)


def _pump_payloads(logs: Sequence[str]) -> list[tuple[int, str]]:
    """(log position, base64 payload) for each Program data line the pump program emitted."""
    stack: list[str] = []
    found: list[tuple[int, str]] = []
    for position, line in enumerate(logs):
        if line.startswith(_DATA_PREFIX):
            if stack and stack[-1] == PUMP_PROGRAM_ID:
                found.append((position, line[len(_DATA_PREFIX) :]))
            continue
        invoked = _INVOKE.fullmatch(line)
        if invoked is not None:
            stack.append(invoked.group(1))
            continue
        if stack and _RESULT.fullmatch(line) is not None:
            stack.pop()
    return found


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
        self._boundary = boundary
        self._clock = clock
        self._watch = watch
        self._bridge = bridge
        self._limiter = limiter
        self._dedup = DedupWindow(capacity=dedup_capacity)
        self._stats = FeedStats()
        self._gaps = GapLedger(clock, sink=bridge.recorder.record_gap)
        self._recovery = Recovery(
            clock=clock,
            supervisor=supervisor,
            frames=frames,
            gaps=self._gaps,
            subscribe=self._subscribe_once,
            held=lambda: watch.held,
        )

    @property
    def stats(self) -> FeedStats:
        return self._stats

    @property
    def gaps(self) -> GapLedger:
        return self._gaps

    async def subscribe(self) -> None:
        await self._subscribe_once()

    async def _subscribe_once(self) -> None:
        await self._limiter.acquire()
        await self._boundary.rpc(
            "logsSubscribe",
            [{"mentions": [PUMP_PROGRAM_ID]}, {"commitment": "confirmed"}],
        )

    async def pump_once(self) -> None:
        frame = await self._recovery.receive()
        if frame is None:
            return
        self._stats.received += 1
        await self._handle(frame)

    async def _handle(self, frame: object) -> None:
        extracted = _notification_value(frame)
        if extracted is None:
            self._stats.malformed += 1
            return
        signature, err, logs = extracted
        if err is not None:
            self._stats.failed_tx += 1
            return
        if _TRUNCATED in logs:
            full = await self._full_logs(signature)
            if full is None:
                return
            logs = full
        for position, payload in _pump_payloads(logs):
            if not self._dedup.admit((signature, position)):
                self._stats.duplicate += 1
                continue
            await self._apply(payload, signature, position)

    async def _full_logs(self, signature: str) -> list[str] | None:
        await self._limiter.acquire()
        try:
            response = await self._boundary.rpc(
                "getTransaction",
                [
                    signature,
                    {
                        "encoding": "json",
                        "commitment": "confirmed",
                        "maxSupportedTransactionVersion": 0,
                    },
                ],
            )
        except TRANSPORT_FAILURES:
            self._gaps.record_loss("logs_truncated_unrecovered")
            return None
        result = response.get("result") if isinstance(response, dict) else None
        meta = result.get("meta") if isinstance(result, dict) else None
        if not isinstance(meta, dict) or not _is_list_of_str(meta.get("logMessages")):
            self._stats.malformed += 1
            return None
        if meta.get("err") is not None:
            self._stats.failed_tx += 1
            return None
        return list(meta["logMessages"])

    async def _apply(self, payload: str, signature: str, position: int) -> None:
        try:
            event = decode_program_data(payload)
        except EventDecodeError:
            self._stats.undecodable += 1
            return
        if not isinstance(event, (TradeEvent, PostCompleteBuyEvent)):
            return
        if event.mint not in self._watch:
            self._stats.unwatched += 1
            return
        occurred_at = self._clock.utc_iso()
        if isinstance(event, TradeEvent):
            observation = CurveObservation(
                mint=event.mint,
                ts_utc=occurred_at,
                s_lamports=event.virtual_sol_reserves,
                t_units=event.virtual_token_reserves,
                complete=False,
                source="rpc",
            )
            try:
                observation.validate()
            except ValueError:
                self._stats.undecodable += 1
                return
            await self._bridge.publish(observation)
        await self._bridge.publish_market_event(
            kind=EventKind.trade,
            mint=event.mint,
            occurred_at=occurred_at,
            payload={
                "signature": signature,
                "position": position,
                "user": event.user,
                "is_buy": isinstance(event, TradeEvent) and event.is_buy,
            },
            lamports=event.sol_amount,
            token_units=event.token_amount,
        )
        self._stats.applied += 1
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
