"""logsSubscribe trade feed (R46): bounded follow-ups through one limiter.

Trade events come from ``logsSubscribe`` on bonding-curve accounts; each
trade signature may take a bounded ``getTransaction`` follow-up through the
shared limiter. Malformed frames raise into the error path and count as
unknown; ``extra="forbid"`` models reject unexpected fields.
"""

from __future__ import annotations

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
