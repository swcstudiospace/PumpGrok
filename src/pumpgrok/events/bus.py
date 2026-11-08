"""Per-entity lanes over a sidecar: write-ahead P0/P1, retries, DLQ, bounded shutdown."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable, Coroutine
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

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
    SHUTDOWN_TIMEOUT_S,
)
from pumpgrok.events.errors import EventBusClosed, PoisonEvent, TransientEvent
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


class _Outcome(StrEnum):
    """How one handler attempt, or one retry decision, ended."""

    OK = "ok"
    POISON = "poison"
    TRANSIENT = "transient"
    # A P2 retry woke after a newer publish for its key. The event goes to the DLQ.
    STALE = "stale"
    # Shutdown cancelled a handler call that outlived SHUTDOWN_TIMEOUT_S. The event stays pending.
    INTERRUPTED = "interrupted"


class EventBus:
    """Per-entity FIFO lanes for P0/P1, latest-wins slots for P2. Time comes only from the clock.

    Invariants:
    - With a store, accepting a P0/P1 event is one transaction: its dedup row plus a pending
      row (queued) or a DLQ row (overflow). If it raises, publish raises that error and
      nothing is remembered, queued, or saved.
    - P0/P1 success is one transaction: applied row plus pending delete. P0/P1 failure
      (poison, or transient retries exhausted) is one transaction: DLQ row plus pending delete.
    - P2 writes no dedup, applied, or pending row at accept. Its dedup set is in memory. Success
      deletes any pending row for the id and writes no applied row. Failure writes a DLQ row.
      Active state and the in-memory id are released only after the handoff succeeds.
    - A P2 key's lock is held only around handler calls. Retry backoff holds no lock. A retry
      superseded by a newer publish goes to the DLQ with reason transient, even at shutdown.
    - shutdown() sets closing, cancels every pending wait, gives running handler calls
      SHUTDOWN_TIMEOUT_S on the clock to return, then cancels the rest. A cancelled event
      stays pending: not applied and not in the DLQ. Worker tasks get one more
      SHUTDOWN_TIMEOUT_S; stragglers keep running. Unfinished P2 events are then written
      to pending, except terminal stale retries whose durable DLQ handoff must finish first.
    - recover() runs each pending P0/P1 event once. A row with an applied mark is completed
      without running the handler. Each pending P2 event runs once.
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
        self._tasks: dict[tuple[int, str], asyncio.Task[None]] = {}
        self._p2: dict[str, deque[Event]] = {}
        self._p2_gen: dict[str, int] = {}
        # P2 events claimed from a slot and not yet settled, keyed by event id.
        self._p2_active: dict[str, Event] = {}
        # Keep retry generations until handoff, including failed DLQ writes and shutdown.
        self._p2_retry_gen: dict[str, int] = {}
        self._p2_locks: dict[str, asyncio.Lock] = {}
        # Strong references to every worker task until it finishes.
        self._workers: set[asyncio.Task[None]] = set()
        # Workers suspended in a retry or debounce wait. Shutdown cancels these.
        self._pausing: set[asyncio.Task[Any]] = set()
        # Workers suspended inside a handler call. Shutdown waits on these, then cancels them.
        self._in_handler: set[asyncio.Task[Any]] = set()
        self._closing = asyncio.Event()
        self._abandoning = False
        self._shut_down = False
        self._shutdown_lock = asyncio.Lock()
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
        if self._closing.is_set():
            raise EventBusClosed()
        priority = priority_of(event.kind)
        if priority == 2:
            self._publish_p2(event)
            return
        await self._publish_durable(event, priority)

    async def start(self) -> None:
        if self._closing.is_set():
            raise EventBusClosed()
        self._started = True
        for priority, entity_id in list(self._lanes):
            self._kick(priority, entity_id)
        for key, slot in list(self._p2.items()):
            if slot:
                self._kick_p2(key, slot[-1].kind)

    async def shutdown(self) -> None:
        """Stop accepting work and settle what can be settled within SHUTDOWN_TIMEOUT_S.

        Idempotent. Concurrent callers wait for the first call to finish.
        """
        async with self._shutdown_lock:
            if self._shut_down:
                return
            self._closing.set()
            for task in list(self._pausing):
                task.cancel()
            await self._await_handlers()
            self._abandoning = True
            for task in list(self._in_handler):
                task.cancel()
            await self._join_workers()
            self._persist_unfinished_p2()
            self._shut_down = True

    async def recover(self) -> None:
        """Run every pending row in seq order. Call before publish() on a fresh bus."""
        if self._closing.is_set():
            raise EventBusClosed()
        if self._store is None:
            return
        await self._spawn(self._recover_pending())

    async def _recover_pending(self) -> None:
        store = self._store
        if store is None:
            return
        for event in store.load_pending():
            if self._closing.is_set():
                return
            if priority_of(event.kind) != 2 and store.is_applied(event.event_id):
                store.complete_applied(event.event_id, self._clock.now())
                continue
            if not await self._run_once(event):
                return

    async def _publish_durable(self, event: Event, priority: int) -> None:
        full = _lane_full(priority, self.queued(priority))
        if self._store is not None:
            now = self._clock.now()
            if self._store.is_duplicate(event.event_id, now):
                return
            if full:
                # One transaction. If it raises, nothing is remembered or queued.
                self._store.accept_overflow(event, priority=priority, now=now)
                await self._send_dlq(event)
                return
            self._store.accept_queued(event, priority=priority, now=now)
            self._enqueue(event, priority)
            return
        if event.event_id in self._seen:
            return
        self._seen.add(event.event_id)
        if not full:
            self._enqueue(event, priority)
            return
        try:
            await self._send_dlq(event)
        except BaseException:
            self._seen.discard(event.event_id)
            raise

    def _publish_p2(self, event: Event) -> None:
        if event.event_id in self._seen:
            return
        self._seen.add(event.event_id)
        self._coalesce(event)

    def _enqueue(self, event: Event, priority: int) -> None:
        self._lanes.setdefault((priority, event.entity_id), deque()).append(event)
        self._kick(priority, event.entity_id)

    def _coalesce(self, event: Event) -> None:
        key = _coalesce_key(event.kind, event.entity_id)
        slot = self._p2.setdefault(key, deque())
        if len(slot) >= P2_COALESCE_CAP:
            replaced = slot.pop()
            self._seen.discard(replaced.event_id)
        slot.append(event)
        self._kick_p2(key, event.kind)

    def _kick(self, priority: int, entity_id: str) -> None:
        if not self._started or self._closing.is_set():
            return
        key = (priority, entity_id)
        task = self._tasks.get(key)
        if task is not None and not task.done():
            return
        self._tasks[key] = self._spawn(self._drain(key))

    def _kick_p2(self, key: str, kind: EventKind) -> None:
        if not self._started or self._closing.is_set():
            return
        generation = self._p2_gen.get(key, 0) + 1
        self._p2_gen[key] = generation
        # Each publish gets a delivery task. Older generations return without claiming.
        self._spawn(self._deliver_p2(key, generation, debounce=kind is EventKind.mark))

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        task = asyncio.create_task(coro)
        self._workers.add(task)
        task.add_done_callback(self._workers.discard)
        return task

    async def _drain(self, key: tuple[int, str]) -> None:
        lane = self._lanes[key]
        while lane and not self._closing.is_set():
            if not await self._run_once(lane.popleft()):
                return

    async def _deliver_p2(self, key: str, generation: int, *, debounce: bool) -> None:
        if debounce and not await self._pause(P2_DEBOUNCE_S):
            return
        claimed = await self._claim_and_attempt(key, generation)
        if claimed is None:
            return
        event, outcome = claimed
        if outcome is _Outcome.TRANSIENT:
            self._p2_retry_gen[event.event_id] = generation
        await self._drive(
            event,
            outcome,
            lambda: self._retry_p2(key, generation, event),
            superseded=lambda: self._p2_gen.get(key) != generation,
        )

    async def _claim_and_attempt(self, key: str, generation: int) -> tuple[Event, _Outcome] | None:
        lock = self._p2_lock(key)
        await lock.acquire()
        try:
            event = self._claim_p2(key, generation)
            if event is None:
                return None
            return event, await self._call_once(event)
        finally:
            lock.release()

    def _claim_p2(self, key: str, generation: int) -> Event | None:
        if self._closing.is_set() or self._p2_gen.get(key) != generation:
            return None
        slot = self._p2.get(key)
        if not slot:
            return None
        event = slot.pop()
        slot.clear()
        self._p2_active[event.event_id] = event
        return event

    async def _retry_p2(self, key: str, generation: int, event: Event) -> _Outcome:
        # A newer publish for this key makes this retry stale. Do not wait on the lock for it.
        if self._p2_gen.get(key) != generation:
            return _Outcome.STALE
        lock = self._p2_lock(key)
        await lock.acquire()
        try:
            if self._p2_gen.get(key) != generation:
                return _Outcome.STALE
            if self._closing.is_set():
                return _Outcome.INTERRUPTED
            return await self._call_once(event)
        finally:
            lock.release()

    async def _run_once(self, event: Event) -> bool:
        """Run an event from a lane or from recovery. Return False when shutdown interrupted it."""
        outcome = await self._call_once(event)
        return await self._drive(event, outcome, lambda: self._call_once(event))

    async def _drive(
        self,
        event: Event,
        outcome: _Outcome,
        again: Callable[[], Awaitable[_Outcome]],
        *,
        superseded: Callable[[], bool] | None = None,
    ) -> bool:
        """Settle one claimed event, retrying through `again` as needed.

        Return True when the event reached a terminal state. Return False when shutdown
        left it pending.
        """
        attempts = 0
        while True:
            if outcome is _Outcome.OK:
                self._succeed(event)
                return True
            if outcome is _Outcome.POISON:
                await self._fail(event, "poison")
                return True
            if outcome is _Outcome.STALE:
                await self._fail(event, "transient")
                return True
            if outcome is _Outcome.INTERRUPTED:
                if attempts and superseded is not None and superseded():
                    outcome = _Outcome.STALE
                    continue
                return False
            attempts += 1
            if attempts >= RETRY_ATTEMPTS:
                await self._fail(event, "transient")
                return True
            if not await self._backoff(attempts - 1):
                # Cancelling a backoff must not erase its generation's stale decision.
                if superseded is not None and superseded():
                    outcome = _Outcome.STALE
                    continue
                return False
            outcome = await again()

    async def _call_once(self, event: Event) -> _Outcome:
        """Run the handler on this worker task and report how the attempt ended."""
        task = _own_task()
        self._in_handler.add(task)
        try:
            await self._handler(event)
        except PoisonEvent:
            return _Outcome.POISON
        except TransientEvent:
            return _Outcome.TRANSIENT
        except asyncio.CancelledError:
            if not self._abandoning:
                raise
            # Shutdown cancelled a call that outlived its bound. This is not a handler failure.
            task.uncancel()
            return _Outcome.INTERRUPTED
        finally:
            self._in_handler.discard(task)
        return _Outcome.OK

    async def _backoff(self, step: int) -> bool:
        draw = self._rng.random()
        self.jitters.append(draw)
        return await self._pause(_retry_delay(step, draw))

    async def _pause(self, seconds: float) -> bool:
        """Wait on the clock. Return False when shutdown ends the wait early."""
        if self._closing.is_set():
            return False
        task = _own_task()
        self._pausing.add(task)
        try:
            await self._clock.sleep(seconds)
        except asyncio.CancelledError:
            if not self._closing.is_set():
                raise
            task.uncancel()
            return False
        finally:
            self._pausing.discard(task)
        return not self._closing.is_set()

    def _forget_p2(self, event: Event) -> None:
        if priority_of(event.kind) == 2:
            self._p2_active.pop(event.event_id, None)
            self._p2_retry_gen.pop(event.event_id, None)
            self._seen.discard(event.event_id)

    def _succeed(self, event: Event) -> None:
        if priority_of(event.kind) == 2:
            if self._store is not None:
                self._store.delete_pending(event.event_id)
            # A delivered P2 id leaves the in-memory dedup set. The design sets no P2 TTL.
            self._forget_p2(event)
            return
        if self._store is not None:
            self._store.complete_applied(event.event_id, self._clock.now())

    async def _fail(self, event: Event, reason: str) -> None:
        if self._store is not None:
            self._store.fail_to_dlq(event, reason=reason)
            self._forget_p2(event)
            await self._send_dlq(event)
        else:
            await self._send_dlq(event)
            self._forget_p2(event)

    async def _send_dlq(self, event: Event) -> None:
        result = self._dlq(event)
        if result is not None:
            await result

    async def _await_handlers(self) -> None:
        """Wait up to SHUTDOWN_TIMEOUT_S on the clock for running handler calls to return."""
        if not self._in_handler:
            return
        timer = asyncio.ensure_future(self._clock.sleep(SHUTDOWN_TIMEOUT_S))
        try:
            while self._in_handler:
                await asyncio.wait(
                    {timer, *self._in_handler},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if timer.done():
                    return
        finally:
            timer.cancel()

    async def _join_workers(self) -> None:
        """Wait up to SHUTDOWN_TIMEOUT_S on the clock for worker tasks. Stragglers keep running."""
        timer = asyncio.ensure_future(self._clock.sleep(SHUTDOWN_TIMEOUT_S))
        try:
            while self._workers:
                await asyncio.wait({timer, *self._workers}, return_when=asyncio.FIRST_COMPLETED)
                if timer.done():
                    return
        finally:
            timer.cancel()

    def _p2_lock(self, key: str) -> asyncio.Lock:
        lock = self._p2_locks.get(key)
        if lock is None:
            lock = self._p2_locks[key] = asyncio.Lock()
        return lock

    def _persist_unfinished_p2(self) -> None:
        """Persist unfinished P2 work without turning terminal stale retries into fresh work."""
        if self._store is None:
            return
        # A retry may have failed its durable handoff or outlived the worker join bound.
        # Keep its generation's stale disposition; a failed write keeps the active id and
        # raises from shutdown rather than parking that retry as fresh pending.
        # This is a durable write only: notification callbacks cannot add a third shutdown wait.
        for event_id, generation in tuple(self._p2_retry_gen.items()):
            event = self._p2_active[event_id]
            if self._p2_gen.get(_coalesce_key(event.kind, event.entity_id)) == generation:
                continue
            self._store.fail_to_dlq(event, reason="transient")
            self._forget_p2(event)
        # Claimed events (retrying or in flight) precede queued ones.
        events = list(self._p2_active.values())
        for slot in self._p2.values():
            events.extend(slot)
        self._store.replace_pending(events)


def _own_task() -> asyncio.Task[Any]:
    task = asyncio.current_task()
    if task is None:
        raise RuntimeError("event bus work must run inside a task")
    return task


def _retry_delay(step: int, draw: float) -> float:
    base = min(BACKOFF_INITIAL_S * BACKOFF_FACTOR**step, BACKOFF_MAX_S)
    return float(base) + draw * BACKOFF_JITTER_S


def _lane_full(priority: int, queued: int) -> bool:
    cap = _LANE_CAP[priority]
    return cap is not None and queued >= cap


def _coalesce_key(kind: EventKind, entity_id: str) -> str:
    return f"{kind.value}:{entity_id}"
