"""In-memory lanes plus sidecar dedup, retry, and pending recovery."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol

from pumpgrok.events.constants import (
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
    """Per-entity FIFO lanes. Time comes only from the injected clock."""

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
        self._tasks: dict[tuple[int, str], asyncio.Task[None]] = {}
        self._p2: dict[str, deque[Event]] = {}
        self._p2_gen: dict[str, int] = {}
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
        return sum(len(lane) for (lane_priority, _), lane in self._lanes.items() if lane_priority == priority)

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
            self._seen.add(event.event_id)
            self._coalesce(event)
            return
        if _lane_full(priority, self.queued(priority)):
            await self._overflow(event)
            return
        self._accept(event, priority)
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
            if self._store.is_applied(event.event_id):
                self._store.delete_pending(event.event_id)
                continue
            await self._invoke(event)
            self._store.mark_applied(event.event_id, self._clock.now())
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
        previous = self._p2_tasks.get(key)
        if previous is not None and not previous.done():
            previous.cancel()
        if kind is EventKind.mark:
            self._p2_tasks[key] = asyncio.create_task(self._deliver_mark(key, generation))
            return
        self._p2_tasks[key] = asyncio.create_task(self._deliver_latest(key, generation))

    async def _drain(self, key: tuple[int, str]) -> None:
        lane = self._lanes[key]
        while lane:
            event = lane.popleft()
            await self._invoke(event)

    async def _deliver_latest(self, key: str, generation: int) -> None:
        if self._p2_gen.get(key) != generation:
            return
        slot = self._p2.get(key)
        if not slot:
            return
        event = slot.pop()
        slot.clear()
        await self._handler(event)

    async def _deliver_mark(self, key: str, generation: int) -> None:
        try:
            await self._clock.sleep(P2_DEBOUNCE_S)
        except asyncio.CancelledError:
            return
        if self._p2_gen.get(key) != generation:
            return
        slot = self._p2.get(key)
        if not slot:
            return
        event = slot.pop()
        slot.clear()
        await self._handler(event)

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

    async def _invoke(self, event: Event) -> None:
        attempts = 0
        while True:
            try:
                await self._handler(event)
            except PoisonEvent:
                await self._fail(event, "poison")
                return
            except TransientEvent:
                attempts += 1
                if attempts >= RETRY_ATTEMPTS:
                    await self._fail(event, "transient")
                    return
                self.jitters.append(self._rng.random())
                continue
            else:
                if self._store is not None:
                    self._store.mark_applied(event.event_id, self._clock.now())
                return

    async def _fail(self, event: Event, reason: str) -> None:
        if self._store is not None:
            self._store.write_dlq(event, reason=reason)
        await self._send_dlq(event)

    def _queued_events(self) -> list[Event]:
        queued: list[Event] = []
        for lane in self._lanes.values():
            queued.extend(lane)
        for slot in self._p2.values():
            queued.extend(slot)
        return queued


def _lane_full(priority: int, queued: int) -> bool:
    cap = _LANE_CAP[priority]
    return cap is not None and queued >= cap


def _coalesce_key(kind: EventKind, entity_id: str) -> str:
    return f"{kind.value}:{entity_id}"
