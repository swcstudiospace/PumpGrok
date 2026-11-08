"""In-memory lanes plus sidecar dedup, retry, and pending recovery."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol

from pumpgrok.events.constants import (
    BACKOFF_FACTOR,
    BACKOFF_INITIAL_S,
    BACKOFF_JITTER_S,
    BACKOFF_MAX_S,
    P0_LANE_CAP,
    P1_LANE_CAP,
    P2_COALESCE_CAP,
    P2_DEBOUNCE_S,
    RETRY_ATTEMPTS,
)
from pumpgrok.events.errors import PoisonEvent, TransientEvent
from pumpgrok.events.models import Event, EventKind, priority_of
from pumpgrok.events.store import EventStore
from pumpgrok.replay.clock import Clock
from pumpgrok.replay.rng import make_rng

if TYPE_CHECKING:
    from pumpgrok.config.settings import Settings

Handler = Callable[[Event], Awaitable[None]]
Dlq = Callable[[Event], Awaitable[None] | None]

_LANE_CAP = {0: P0_LANE_CAP, 1: P1_LANE_CAP}


class _Jitter(Protocol):
    def random(self) -> float: ...


class EventBus:
    """Per-entity FIFO lanes. Time comes only from the injected clock.

    Invariants:
    - An event whose handler is running stays in an in-flight slot until its handler
      returns, so shutdown() saves it to pending.
    - An event is marked applied only after its handler returned normally. A failed event
      goes to the DLQ unapplied, so a DLQ replay can run it again.
    - A P0/P1 event that overflows is recorded in the same dedup state as an accepted
      event. A P2 id leaves the dedup set once it is delivered.
    """

    def __init__(
        self,
        *,
        clock: Clock,
        handler: Handler,
        dlq: Dlq,
        store: EventStore | None = None,
        rng: _Jitter | None = None,
    ) -> None:
        self._clock = clock
        self._handler = handler
        self._dlq = dlq
        self._store = store
        self._rng = rng if rng is not None else make_rng()
        self.jitters: list[float] = []
        self._seen: set[str] = set()
        self._lanes: dict[tuple[int, str], deque[Event]] = {}
        self._lane_inflight: dict[tuple[int, str], Event] = {}
        self._tasks: dict[tuple[int, str], asyncio.Task[None]] = {}
        self._p2: dict[str, deque[Event]] = {}
        self._p2_gen: dict[str, int] = {}
        self._p2_inflight: dict[str, Event] = {}
        self._p2_locks: dict[str, asyncio.Lock] = {}
        # Strong references so a waiting delivery task is not garbage collected.
        self._p2_tasks: dict[str, asyncio.Task[None]] = {}
        self._started = False

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        clock: Clock,
        handler: Handler,
        dlq: Dlq,
        rng: _Jitter | None = None,
    ) -> EventBus:
        path = settings.events.sidecar_path
        return cls(clock=clock, handler=handler, dlq=dlq, store=EventStore(path), rng=rng)

    def queued(self, priority: int) -> int:
        return sum(
            len(lane)
            for (lane_priority, _), lane in self._lanes.items()
            if lane_priority == priority
        )

    def pending_p2(self, kind: EventKind, entity_id: str) -> Event | None:
        slot = self._p2.get(_coalesce_key(kind, entity_id))
        if not slot:
            return None
        return slot[-1]

    async def publish(self, event: Event) -> None:
        priority = priority_of(event.kind)
        if self._suppressed(event, priority):
            return
        if priority == 2:
            self._accept(event, priority)
            self._coalesce(event)
            return
        # Overflow is recorded like an accepted event, so a duplicate publish is suppressed
        # and a DLQ replay of the overflowed event still runs it exactly once.
        self._accept(event, priority)
        if _lane_full(priority, self.queued(priority)):
            await self._overflow(event)
            return
        lane = self._lanes.setdefault((priority, event.entity_id), deque())
        lane.append(event)
        self._kick(priority, event.entity_id)

    async def start(self) -> None:
        self._started = True
        for priority, entity_id in list(self._lanes):
            self._kick(priority, entity_id)
        for key, slot in list(self._p2.items()):
            if slot:
                self._kick_p2(key, slot[-1].kind)

    async def shutdown(self) -> None:
        if self._store is None:
            return
        self._store.replace_pending(self._queued_events())

    async def recover(self) -> None:
        if self._store is None:
            return
        for event in self._store.load_pending():
            # _invoke marks applied only on success. A failed event is now in the DLQ and
            # unapplied. Its pending row is dropped, so only a DLQ replay runs it again.
            if not self._store.is_applied(event.event_id):
                await self._invoke(event)
            self._store.delete_pending(event.event_id)

    def _coalesce(self, event: Event) -> None:
        key = _coalesce_key(event.kind, event.entity_id)
        slot = self._p2.setdefault(key, deque())
        if len(slot) >= P2_COALESCE_CAP:
            replaced = slot.pop()
            self._seen.discard(replaced.event_id)
        slot.append(event)
        self._kick_p2(key, event.kind)

    def _kick(self, priority: int, entity_id: str) -> None:
        if not self._started:
            return
        key = (priority, entity_id)
        task = self._tasks.get(key)
        if task is not None and not task.done():
            return
        self._tasks[key] = asyncio.create_task(self._drain(key))

    def _kick_p2(self, key: str, kind: EventKind) -> None:
        if not self._started:
            return
        generation = self._p2_gen.get(key, 0) + 1
        self._p2_gen[key] = generation
        # A running handler is never cancelled. The newer generation waits on the key lock,
        # then delivers whatever the slot holds, so the newest value runs once afterwards.
        self._p2_tasks[key] = asyncio.create_task(
            self._deliver_p2(key, generation, debounce=kind is EventKind.mark)
        )

    async def _drain(self, key: tuple[int, str]) -> None:
        lane = self._lanes[key]
        while lane:
            event = lane.popleft()
            self._lane_inflight[key] = event
            await self._invoke(event)
            del self._lane_inflight[key]

    async def _deliver_p2(self, key: str, generation: int, *, debounce: bool) -> None:
        if debounce:
            await self._clock.sleep(P2_DEBOUNCE_S)
        lock = self._p2_locks.get(key)
        if lock is None:
            lock = self._p2_locks[key] = asyncio.Lock()
        async with lock:
            if self._p2_gen.get(key) != generation:
                return
            slot = self._p2.get(key)
            if not slot:
                return
            event = slot.pop()
            slot.clear()
            self._p2_inflight[key] = event
            await self._invoke(event)
            del self._p2_inflight[key]
            # Delivered: the id no longer needs dedup. Design docs set no P2 TTL.
            self._seen.discard(event.event_id)

    async def _send_dlq(self, event: Event) -> None:
        result = self._dlq(event)
        if result is not None:
            await result

    def _suppressed(self, event: Event, priority: int) -> bool:
        if priority in (0, 1) and self._store is not None:
            return self._store.is_duplicate(event.event_id, self._clock.now())
        return event.event_id in self._seen

    def _accept(self, event: Event, priority: int) -> None:
        if priority in (0, 1) and self._store is not None:
            self._store.remember(event.event_id, priority, self._clock.now())
            return
        self._seen.add(event.event_id)

    async def _overflow(self, event: Event) -> None:
        if self._store is not None:
            self._store.write_dlq(event, reason="overflow")
        await self._send_dlq(event)

    async def _invoke(self, event: Event) -> bool:
        """Run the handler with bounded retries. Return True only when the handler returned.

        Poison and exhausted transient failures go to the DLQ and return False.
        """
        attempts = 0
        while True:
            try:
                await self._handler(event)
            except PoisonEvent:
                await self._fail(event, "poison")
                return False
            except TransientEvent:
                attempts += 1
                if attempts >= RETRY_ATTEMPTS:
                    await self._fail(event, "transient")
                    return False
                draw = self._rng.random()
                self.jitters.append(draw)
                await self._clock.sleep(_retry_delay(attempts - 1, draw))
            else:
                if self._store is not None:
                    self._store.mark_applied(event.event_id, self._clock.now())
                return True

    async def _fail(self, event: Event, reason: str) -> None:
        if self._store is not None:
            self._store.write_dlq(event, reason=reason)
        await self._send_dlq(event)

    def _queued_events(self) -> list[Event]:
        # Each in-flight event is the oldest for its key, so it is listed before the queue.
        queued: list[Event] = []
        for key, lane in self._lanes.items():
            inflight = self._lane_inflight.get(key)
            if inflight is not None:
                queued.append(inflight)
            queued.extend(lane)
        for p2_key, slot in self._p2.items():
            inflight = self._p2_inflight.get(p2_key)
            if inflight is not None:
                queued.append(inflight)
            queued.extend(slot)
        return queued


def _retry_delay(step: int, draw: float) -> float:
    base = min(BACKOFF_INITIAL_S * BACKOFF_FACTOR**step, BACKOFF_MAX_S)
    return float(base) + draw * BACKOFF_JITTER_S


def _lane_full(priority: int, queued: int) -> bool:
    cap = _LANE_CAP[priority]
    return cap is not None and queued >= cap


def _coalesce_key(kind: EventKind, entity_id: str) -> str:
    return f"{kind.value}:{entity_id}"
