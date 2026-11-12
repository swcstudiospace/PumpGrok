"""Read-only Solana logs feed for pump program trades, with bounded recovery.

One ``logsSubscribe`` filter mentions the pump program. A notification's ``Program data:``
lines are attributed to the pump program by the invoke stack, so a payload emitted by
another program in the same transaction is never decoded as a pump event. Event identity
is ``(signature, log position)``, which keeps distinct events in one transaction apart and
collapses a repeated notification. Failed transactions are ignored. ``getTransaction`` is
read only when a notification's logs were truncated by the node.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

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


def _is_list_of_str(value: object) -> bool:
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
