"""Roster-order asyncio supervisor over ten seat tasks."""

from __future__ import annotations

import asyncio
import functools
import hashlib
import logging
import math
import sqlite3
from collections.abc import Awaitable, Callable, Mapping
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pumpgrok.core.ids import Clock
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS
from pumpgrok.core.risk_budget import RiskBudget, budget_equity_lamports
from pumpgrok.execution.deposits import position_deposits_by_seq
from pumpgrok.ledger.autonomy import read_autonomy
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.reducer import initial_state, reduce
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.views import equity_lamports
from pumpgrok.replay.clock import format_ts_utc
from pumpgrok.risk.engine import utc_day
from pumpgrok.supervisor.health import (
    HEALTH_FILE_INTERVAL_S,
    build_status,
    write_health_json,
)
from pumpgrok.supervisor.scheduler.degraded import DegradedState, kill_switch_engaged
from pumpgrok.supervisor.seat_relay import relay_tail
from pumpgrok.supervisor.seat_restart import ObserveOnly
from pumpgrok.supervisor.seat_task import SeatContext, SeatTask

if TYPE_CHECKING:
    from pumpgrok.events.models import Event
    from pumpgrok.tools.notify.notifier import Notifier

log = logging.getLogger("pumpgrok.supervisor.scheduler")

#: The bus event that woke the running cycle in event mode; None for a timer or cadence start.
TRIGGER_EVENT: ContextVar[Event | None] = ContextVar("pumpgrok_trigger_event", default=None)

#: Supervisor tick: due seats are started once per tick, in roster order.
TICK_S = 1.0

#: Per-seat cadence in seconds (paper-engine.md 6.2). Sniper and signal are
#: queue-driven; a 1 s cadence polls the queue without busy-looping.
SEAT_CADENCES: dict[str, float] = {
    "bot-00-chief": 60.0,
    "bot-01-scout": 10.0,
    "bot-02-risk": 5.0,
    "bot-03-whale": 120.0,
    "bot-04-sniper": 1.0,
    "bot-05-rug": 30.0,
    "bot-06-exit": 15.0,
    "bot-07-shill": 300.0,
    "bot-08-signal": 1.0,
    "bot-09-journal": 300.0,
}

ROSTER: tuple[str, ...] = EXPECTED_SEAT_IDS

#: Wake modes: ``cadence`` (per-seat periods, the default) and ``event`` (EVT-10 bus wakes).
WAKE_MODES: tuple[str, ...] = ("cadence", "event")


def cycle_timeout_s(cadence_s: float) -> float:
    """Cycle timeout: max(30 s, 4 x cadence), counted as a crash."""
    return max(30.0, 4.0 * cadence_s)


def rollover_key(day_utc: str) -> str:
    """Idempotency per UTC day: one ``DailyRollover`` per day (D6).

    Same domain-separated shape as ``risk.engine.halt_key`` so a replayed
    day never appends a second rollover row.
    """
    return hashlib.sha256(f"DailyRollover|{day_utc}".encode()).hexdigest()


def _seat_timing(
    seat: str, *, seat_cadences: Mapping[str, float] | None, event_mode: bool
) -> tuple[float, float]:
    """(cadence_s, stale_cadence_s) for one seat under the wake mode.

    Cadence mode is the table, unchanged. Event mode: a timed seat runs on its EVENT_TIMERS
    period, which is also its heartbeat grace. An event-only seat has no timer, so it is never
    stale by time; its cadence only sizes the cycle timeout.
    """
    from pumpgrok.supervisor.scheduler import EVENT_TIMERS as _EVT  # noqa: PLC0415

    overrides = seat_cadences or {}
    if not event_mode:
        return overrides.get(seat, SEAT_CADENCES[seat]), SEAT_CADENCES[seat]
    if seat in _EVT:
        return overrides.get(seat, _EVT[seat]), _EVT[seat]
    return overrides.get(seat, SEAT_CADENCES[seat]), math.inf


class Supervisor:
    """Roster-order asyncio supervisor over ten seat tasks."""

    def __init__(
        self,
        *,
        store: LedgerStore,
        clock: Clock,
        rng: Any,
        cycles: Mapping[str, Callable[[SeatContext], Awaitable[Mapping[str, Any] | None]]],
        mode: str = "paper",
        source: str = "paper",
        correlation_id: str = "desk",
        notifier: Notifier | None = None,
        degraded: DegradedState | None = None,
        health_path: str | Path | None = None,
        risk: Any | None = None,
        budget: RiskBudget | None = None,
        cycle_observer: Callable[[str, float, str], None] | None = None,
        seat_cadences: Mapping[str, float] | None = None,
        wake_mode: str = "cadence",
    ) -> None:
        unknown = set(cycles) - set(ROSTER)
        if unknown:
            raise ValueError(f"unknown seats in cycle map: {sorted(unknown)}")
        missing = [seat for seat in ROSTER if seat not in cycles]
        if missing:
            raise ValueError(f"cycle map missing seats: {missing}")
        if wake_mode not in WAKE_MODES:
            raise ValueError(f"unknown wake_mode {wake_mode!r}; expected one of {WAKE_MODES}")
        self._store = store
        self._clock = clock
        self._rng = rng
        self._mode = mode
        self._source = source
        self._correlation_id = correlation_id
        self._notifier = notifier
        self._degraded = degraded if degraded is not None else DegradedState()
        self._health_path = Path(health_path) if health_path is not None else None
        self._risk = risk
        self._budget = budget if budget is not None else RiskBudget()
        self.observe_only = ObserveOnly()
        self._event_mode = wake_mode == "event"
        self.tasks: dict[str, SeatTask] = {}
        for seat in ROSTER:
            cadence_s, stale_cadence_s = _seat_timing(
                seat, seat_cadences=seat_cadences, event_mode=self._event_mode
            )
            self.tasks[seat] = SeatTask(
                seat,
                cadence_s,
                cycles[seat],
                clock=clock,
                rng=rng,
                store=store,
                source=source,
                correlation_id=correlation_id,
                notifier=notifier,
                observe_only=self.observe_only,
                cycle_observer=cycle_observer,
                stale_cadence_s=stale_cadence_s,
            )
        # Restored latches (rebuilt from the ledger as each SeatTask is constructed) reach the
        # risk engine now, before the first seat cycle, not only at the end of a tick. A failure
        # propagates: a supervisor must not start with buys unlatched.
        if self._risk is not None:
            self._risk.set_observe_only(self.observe_only.seats())
        self._stop = asyncio.Event()
        self._relay_cursor = 0
        self._started_at = clock.now()
        self._last_health_write = 0.0
        self._last_rollover_day: str | None = None
        self._inflight: dict[str, asyncio.Task[str]] = {}
        self._seat_locks: dict[str, asyncio.Lock] = {seat: asyncio.Lock() for seat in ROSTER}

    @property
    def clock(self) -> Clock:
        """Injected clock (lifecycle drains against it)."""
        return self._clock

    @property
    def degraded(self) -> DegradedState:
        """Live degraded-mode probes."""
        return self._degraded

    def running_tasks(self) -> list[asyncio.Task[Any]]:
        """Live seat cycle tasks this supervisor started.

        Scoped to the supervisor's own seats: a caller awaiting the service (for
        example ``serve_replay`` run as a task) is never drained or cancelled.
        """
        return [task for task in self._inflight.values() if not task.done()]

    def request_stop(self, source: str) -> None:
        """Idempotent stop: a second signal logs and never forces."""
        if self._stop.is_set():
            log.info("stop already requested (source=%s); not forcing", source)
            return
        log.info("stop requested (source=%s)", source)
        self._stop.set()

    @property
    def stopped(self) -> bool:
        """Whether a stop was requested."""
        return self._stop.is_set()

    def autonomy_level(self) -> str:
        """Operator-ledger level at PAPER_LEDGER_PATH; live mode always forces manual-ticket.

        Read-only and never created: a missing operator ledger reads as manual-ticket, the same
        rule the promotion path applies. The replay store never carries the human level.
        """
        if self._mode == "live":
            return "manual-ticket"
        try:
            if not PAPER_LEDGER_PATH.exists():
                return "manual-ticket"
            operator = LedgerStore(str(PAPER_LEDGER_PATH))
            try:
                return read_autonomy(operator)
            finally:
                operator.close()
        except Exception:
            return "manual-ticket"

    def _seat_context(self, seat: str) -> SeatContext:
        return SeatContext(
            seat_id=seat,
            clock=self._clock,
            rng=self._rng,
            store=self._store,
            autonomy_level=self.autonomy_level(),
            observe_only=self.observe_only.is_latched(seat),
            source=self._source,
            correlation_id=self._correlation_id,
            degraded=self._degraded,
        )

    def _begin_tick(self) -> dict[str, str]:
        """Record the day's rollover, then start every due seat; nothing is awaited."""
        self._emit_rollover(self._clock.now())
        return self._start_due()

    def _timer_due(self, seat: str, now: float) -> bool:
        """Timer start: any seat in cadence mode; only EVENT_TIMERS seats in event mode."""
        from pumpgrok.supervisor.scheduler import EVENT_TIMERS as _EVT  # noqa: PLC0415

        if self._event_mode and seat not in _EVT:
            return False
        return self.tasks[seat].is_due(now)

    def _timed_seats(self) -> tuple[str, ...]:
        """Seats with a heartbeat: the roster in cadence mode, EVENT_TIMERS in event mode."""
        from pumpgrok.supervisor.scheduler import EVENT_TIMERS as _EVT  # noqa: PLC0415

        if self._event_mode:
            return tuple(seat for seat in ROSTER if seat in _EVT)
        return ROSTER

    def _spawn_cycle(self, seat: str, event: Event | None = None) -> asyncio.Task[str]:
        """Start one seat cycle as a task. Event mode serializes each seat behind its own lock."""
        if self._event_mode:
            return asyncio.ensure_future(self._serial_cycle(seat, event))
        return asyncio.ensure_future(self.tasks[seat].run_guarded(self._seat_context(seat)))

    async def _serial_cycle(self, seat: str, event: Event | None) -> str:
        """Event mode: a seat never overlaps itself, whether woken by an event or its timer.

        The triggering event is visible to the cycle through ``TRIGGER_EVENT``. The task owns
        its context, so a timer start (``event=None``) never sees another wake's event.
        """
        async with self._seat_locks[seat]:
            token = TRIGGER_EVENT.set(event)
            try:
                return await self.tasks[seat].run_guarded(self._seat_context(seat))
            finally:
                TRIGGER_EVENT.reset(token)

    async def _await_cycle(self, seat: str, event: Event | None = None) -> str:
        """Run one seat cycle to completion and return its outcome."""
        child = self._spawn_cycle(seat, event)
        self._inflight[seat] = child
        try:
            return await child
        except asyncio.CancelledError:
            child.cancel()
            raise
        finally:
            if self._inflight.get(seat) is child:
                del self._inflight[seat]

    def _start_due(self) -> dict[str, str]:
        """Start each due seat as its own task, in roster order, without awaiting it.

        A seat whose previous cycle is still running is reported ``"busy"`` and
        not started again, so one seat never overlaps itself.
        """
        now = self._clock.now()
        outcomes: dict[str, str] = {}
        for seat in ROSTER:
            if not self._timer_due(seat, now):
                continue
            running = self._inflight.get(seat)
            if running is not None and not running.done():
                outcomes[seat] = "busy"
                continue
            child = self._spawn_cycle(seat)
            self._inflight[seat] = child
            child.add_done_callback(functools.partial(self._reap, seat))
            outcomes[seat] = "started"
        return outcomes

    def _reap(self, seat: str, child: asyncio.Task[str]) -> None:
        """Forget a finished seat task; log a cycle failure nobody awaited."""
        if self._inflight.get(seat) is child:
            del self._inflight[seat]
        if child.cancelled() or child.exception() is None:
            return
        log.error("seat %s cycle task failed: %r", seat, child.exception())

    async def tick_once(self, *, heartbeats: bool = True) -> dict[str, str]:
        """One tick: run the due seats one after another in roster order, then end the tick.

        Sequential, so a seat's order-placing work and its clock effects finish before the
        next seat starts (deterministic on a fixture clock). ``heartbeats=False`` skips the
        cadence staleness check, which a one-shot replay does not use.
        """
        self._emit_rollover(self._clock.now())
        outcomes: dict[str, str] = {}
        for seat in ROSTER:
            if not self._timer_due(seat, self._clock.now()):
                continue  # not due this tick: no outcome is reported, as before
            outcomes[seat] = await self._await_cycle(seat)
        await self._end_of_tick(heartbeats=heartbeats)
        return outcomes

    async def run_once(self) -> dict[str, str]:
        """One full cycle of all ten seats in roster order (AUTO-006).

        Event mode has no cadence to fire on, so a one-shot runs only the timed seats that are
        due; event-only seats run when an event wakes them.
        """
        self._emit_rollover(self._clock.now())
        outcomes: dict[str, str] = {}
        for seat in ROSTER:
            if self._event_mode and not self._timer_due(seat, self._clock.now()):
                continue
            outcomes[seat] = await self._await_cycle(seat)
        # A one-shot cycle runs each seat once; cadence heartbeats apply to the serve loop.
        await self._end_of_tick(heartbeats=False)
        return outcomes

    async def dispatch(self, event: Event) -> dict[str, str]:
        """Event mode: run each seat on the event's wake row once, in roster order (EVT-10)."""
        if not self._event_mode:
            raise RuntimeError("event dispatch requires wake_mode='event'")
        self._emit_rollover(self._clock.now())
        outcomes: dict[str, str] = {}
        from pumpgrok.supervisor.scheduler import wake_order as _wake_order  # noqa: PLC0415

        for seat in _wake_order(event.kind):
            outcomes[seat] = await self._await_cycle(seat, event)
        await self._end_of_tick(heartbeats=False)
        return outcomes

    async def on_event(self, event: Event) -> None:
        """EventBus handler: a delivered event wakes its seats (EVT-10)."""
        await self.dispatch(event)

    async def _end_of_tick(self, *, heartbeats: bool = True) -> None:
        now = self._clock.now()
        resumed = self.observe_only.fold_resume(self._store)
        for seat in resumed:
            log.info("seat %s resumed from observe-only", seat)
        self._sync_risk_latch()
        # RISK-004: live-host ticks poll env, file and alert kill sources every cycle.
        # Replay stays hermetic: its supervisor never reads live kill state.
        if self._risk is not None and self._source != "replay":
            await self._risk.poll_kill_sources()
        if heartbeats:
            for seat in self._timed_seats():
                await self.tasks[seat].check_stale(now)
        self._relay_cursor = await relay_tail(
            self._store, self._notifier, self._clock, self._relay_cursor
        )
        healthy_interval = now - self._last_health_write >= HEALTH_FILE_INTERVAL_S
        if self._health_path is not None and healthy_interval:
            self._last_health_write = now
            try:
                write_health_json(str(self._health_path), self.health_status())
            except OSError as exc:
                log.warning("health.json write failed: %s", exc)

    def _emit_rollover(self, now: float) -> None:
        """Append one ``DailyRollover`` per UTC day, including the first day seen.

        Called at the top of every tick, before any seat runs, so the baseline is
        the account's equity at the day's start. ``run_once_replay`` allows exactly
        these day-keyed rows (5.2 conflict): seat cycles stay read-only while the
        ledger still records one rollover per UTC day (D6).
        """
        day = utc_day(now)
        if self._last_rollover_day == day:
            return
        try:
            self._store.append(
                ts_utc=format_ts_utc(now),
                source=self._source,
                correlation_id=self._correlation_id,
                idempotency_key=rollover_key(day),
                type="DailyRollover",
                payload={
                    "source": self._source,
                    "day_utc": day,
                    "day_start_equity_lamports": self._day_start_equity(now),
                    "prior_day_json": "",
                    "open_positions": [],
                },
            )
        except sqlite3.IntegrityError:
            # Same-day restart: the row already exists; latch the day and stay
            # quiet instead of retrying the doomed insert on every tick.
            self._last_rollover_day = day
            return
        except Exception as exc:
            log.warning("daily rollover append failed: %s", exc)
            return
        self._last_rollover_day = day

    def _day_start_equity(self, now: float) -> int:
        """Account equity folded from the ledger: the day's daily-loss baseline.

        Same fold as ``RiskEngine._fold``: genesis equity from the
        ``initial_equity_lamports`` meta (the default paper budget when absent),
        then every row, marked to the last MTM. This is the ``total`` basis that
        ``EngineLimits`` defaults to, so the halt compares like with like.
        """
        events = self._store.read(since_seq=1, limit=None)
        meta_equity = self._store.get_meta("initial_equity_lamports")
        initial = (
            int(meta_equity) if meta_equity is not None else budget_equity_lamports(self._budget)
        )
        meta_source = self._store.get_meta("source")
        if meta_source:
            source = meta_source
        elif events:
            source = str(events[0]["source"])
        else:
            source = self._source
        state = initial_state(source=source, initial_equity_lamports=initial, day_utc=utc_day(now))
        deposits = position_deposits_by_seq(self._store)
        for event in events:
            state = reduce(state, event, deposits)
        return int(equity_lamports(state))

    def _sync_risk_latch(self) -> None:
        """Mirror the latch set into RiskEngine so buys refuse desk-wide."""
        if self._risk is None:
            return
        try:
            self._risk.set_observe_only(self.observe_only.seats())
        except Exception as exc:
            log.warning("risk latch sync failed: %s", exc)

    def seat_freshness(self) -> dict[str, dict[str, Any]]:
        """Per-seat freshness for health (paper-engine.md 6.6)."""
        now = self._clock.now()
        freshness: dict[str, dict[str, Any]] = {}
        for seat in ROSTER:
            task = self.tasks[seat]
            freshness[seat] = {
                "state": "observe_only" if self.observe_only.is_latched(seat) else "ok",
                "last_ok_ts": task.last_finished_at if task.last_ok else None,
                "stale": task.is_stale(now),
                "cycles": task.cycles,
                "crashes": task.crashes,
            }
        return freshness

    def kill_switch_engaged(self) -> bool:
        """Current kill-switch latch over this supervisor's store (fail-closed)."""
        return kill_switch_engaged(self._store)

    def health_status(self) -> dict[str, Any]:
        """Current /healthz body."""
        return build_status(
            mode=self._mode,
            autonomy_level=self.autonomy_level(),
            ledger_status="CONSISTENT",
            ledger_source=self._source,
            kill_switch=self.kill_switch_engaged(),
            seats=self.seat_freshness(),
            uptime_s=self._clock.now() - self._started_at,
        )

    def ready(self) -> bool:
        """Readyz: ledger CONSISTENT and each timed seat completed one cycle."""
        try:
            consistent = bool(self._store.verify())
        except Exception:
            return False
        return consistent and all(self.tasks[seat].cycles >= 1 for seat in self._timed_seats())

    async def serve_forever(self) -> int:
        """Tick until stop; shutdown owns snapshot/export/health instead.

        Seat cycles run as background tasks: a slow cycle never delays the next
        tick, and ``shutdown`` drains whatever is still running.
        """
        while not self._stop.is_set():
            self._begin_tick()
            await self._end_of_tick()
            await self._clock.sleep(TICK_S)
        return 0
