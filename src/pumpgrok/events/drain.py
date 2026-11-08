"""Synchronous deterministic drain. Does not sleep, verify, or open a ledger."""

from __future__ import annotations

import random
from collections.abc import Sequence

from pumpgrok.core.idempotency import canonical_json
from pumpgrok.events.constants import P2_DEBOUNCE_S
from pumpgrok.events.models import Event, EventKind, priority_of
from pumpgrok.replay.clock import FixtureClock, parse_ts_utc


class DrainBytes(bytes):
    """Delivery log bytes plus the pending count observed when drain returned."""

    pending: int

    def __new__(cls, data: bytes, pending: int) -> DrainBytes:
        value = bytes.__new__(cls, data)
        value.pending = pending
        return value


def drain(events: Sequence[Event], clock: FixtureClock, rng: random.Random) -> DrainBytes:
    """Publish in input order and return canonical delivery bytes.

    A second call with the same events and seed returns equal bytes. It does not
    append to a previous result. Already delivered ids are not appended again.
    Pending is zero when this returns.
    """
    pending = 0
    seen: set[str] = set()
    deliveries: list[dict[str, str]] = []
    marks: dict[str, Event] = {}
    mark_due: dict[str, float] = {}

    def _due(now: float) -> None:
        nonlocal pending
        ready = [key for key, when in mark_due.items() if when <= now]
        for key in sorted(ready, key=lambda item: (mark_due[item], item)):
            event = marks.pop(key)
            mark_due.pop(key)
            pending -= 1
            _record(event)

    def _record(event: Event) -> None:
        jitter = rng.getrandbits(32)
        deliveries.append(
            {
                "entity_id": event.entity_id,
                "event_id": event.event_id,
                "jitter": str(jitter),
                "kind": event.kind.value,
                "outcome": "delivered",
            }
        )

    for event in events:
        if event.event_id in seen:
            continue
        seen.add(event.event_id)
        when = parse_ts_utc(event.occurred_at)
        if when < clock.now():
            raise ValueError("drain events must not move virtual time backwards")
        clock.advance_to(when)
        _due(clock.now())
        priority = priority_of(event.kind)
        if priority == 2 and event.kind is EventKind.mark:
            key = f"{event.kind.value}:{event.entity_id}"
            if key not in marks:
                pending += 1
            marks[key] = event
            mark_due[key] = clock.now() + P2_DEBOUNCE_S
            continue
        _record(event)

    if mark_due:
        clock.advance_to(max(mark_due.values()))
        _due(clock.now())
    elif deliveries:
        clock.advance_to(clock.now())

    payload = canonical_json({"deliveries": deliveries}).encode()
    return DrainBytes(payload, pending)
