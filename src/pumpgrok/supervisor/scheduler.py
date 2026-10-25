"""Ten-seat supervised scheduler (paper-engine.md 6.1-6.2, 6.7).

Within one supervisor tick (``TICK_S = 1`` s) due seats start in roster order
(00..09). Each seat runs its cycle in its own ``asyncio.Task`` under
``clock.timeout(seat_timeout)``; a timed-out cycle counts as a crash. The serve
loop never awaits a cycle, so a slow seat cannot hold other seats or the next
tick, and a seat never overlaps itself. Every wait goes through the injected
clock.

AUTO-005 degraded modes live here as :class:`DegradedState`: LLM fallback,
RPC failover/BLIND, WS reconnect/DataStale, bounded unwritable-ledger
buffer, and clock-skew refusal. AUTO-006 is :func:`run_once_replay`: one
full ten-seat cycle over a fixture through the engine, risk, and paper
adapter, writing ``var/replay/<dataset>/ledger.sqlite`` with no network.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import hashlib
import logging
import os
import sqlite3
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.bot import BotManifest
from pumpgrok.core.ids import Clock, CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, load_bot_manifests
from pumpgrok.core.registry import ToolRegistry
from pumpgrok.core.risk_budget import RiskBudget, budget_equity_lamports
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool
from pumpgrok.engine.pipeline import BUY, CandidateVerdict, decide_replay, evaluate_candidates
from pumpgrok.execution.paper_adapter import PaperAdapter
from pumpgrok.ledger.autonomy import read_autonomy
from pumpgrok.ledger.reducer import initial_state, reduce
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore
from pumpgrok.ledger.views import equity_lamports
from pumpgrok.logging.json import bind_seat
from pumpgrok.replay.clock import FixtureClock, WallClock, format_ts_utc, parse_ts_utc
from pumpgrok.replay.fixtures import FixtureDataset, event_epoch, load_dataset
from pumpgrok.replay.recorder import load_llm_records
from pumpgrok.replay.rng import make_rng
from pumpgrok.replay.runner import (
    REPLAY_ROOT,
    ReplayResult,
    ReplayTrade,
    ledger_events_hash,
    llm_request_for,
    run_replay,
)
from pumpgrok.replay.sources import FixtureCurveSource
from pumpgrok.risk.engine import RiskEngine, utc_day
from pumpgrok.risk.killswitch import env_engaged
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.supervisor.exit_rules import ExitRules, RuleSell
from pumpgrok.supervisor.health import (
    HEALTH_FILE_INTERVAL_S,
    HealthServer,
    build_status,
    write_health_json,
)
from pumpgrok.supervisor.lifecycle import install_signal_handlers, shutdown
from pumpgrok.supervisor.metrics import Metrics
from pumpgrok.supervisor.seat_task import (
    CLOCK_SKEW_S,
    ClockSkew,
    ObserveOnly,
    SeatContext,
    SeatTask,
    relay_tail,
)
from pumpgrok.tools import build_registry
from pumpgrok.tools.exec.place import build_place_tool
from pumpgrok.tools.risk.kill_switch import build_kill_switch_tool

if TYPE_CHECKING:
    from pumpgrok.tools.notify.notifier import Notifier

log = logging.getLogger(__name__)

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

#: WS silence budget before DataStale trips (paper-engine.md 6.7).
WS_STALE_S = 120.0
#: Bounded buffer for orders while the ledger is unwritable (paper-engine.md 6.7).
LEDGER_BUFFER_CAP = 1000


def cycle_timeout_s(cadence_s: float) -> float:
    """Cycle timeout: max(30 s, 4 x cadence), counted as a crash."""
    return max(30.0, 4.0 * cadence_s)


def rollover_key(day_utc: str) -> str:
    """Idempotency per UTC day: one ``DailyRollover`` per day (D6).

    Same domain-separated shape as ``risk.engine.halt_key`` so a replayed
    day never appends a second rollover row.
    """
    return hashlib.sha256(f"DailyRollover|{day_utc}".encode()).hexdigest()


def kill_switch_engaged(store: LedgerStore) -> bool:
    """Shared kill-switch latch for the health body and the metrics gauge.

    True when a ``KillSwitchSet`` row has no later ``KillSwitchCleared``, or
    when ``PUMPGROK_KILLSWITCH`` engages in this process (fail-closed, same
    fold as ``run_halt_status``). File and alert-command sources are enforced
    at decision time by the risk engine; unreadable ledgers report engaged
    rather than all-clear. ``health_status`` and the serve ``_snapshot`` both
    read this so the body and the gauge can never disagree.
    """
    try:
        engaged = env_engaged(os.environ.get("PUMPGROK_KILLSWITCH"))
        for event in store.read(limit=None):
            event_type = event.get("type")
            if event_type == "KillSwitchSet":
                engaged = True
            elif event_type == "KillSwitchCleared":
                engaged = env_engaged(os.environ.get("PUMPGROK_KILLSWITCH"))
        return engaged
    except Exception:
        return True


class LedgerUnavailable(Exception):
    """Ledger unwritable and the bounded buffer is full."""


def assert_no_skew(store: LedgerStore, clock: Clock) -> None:
    """Refuse appends when the clock trails the ledger head beyond 5 s."""
    events = store.read(limit=None)
    if not events:
        return
    head_ts = parse_ts_utc(str(events[-1].get("ts_utc", "")))
    if DegradedState.skew_detected(clock.now(), head_ts):
        raise ClockSkew(f"clock trails ledger head by over {CLOCK_SKEW_S:.0f}s")


@dataclass
class DegradedState:
    """AUTO-005 degraded-mode probes and behavior switches (paper-engine.md 6.7).

    Every field has a setter (the seat cycles feed observations) and a
    behavior query (the scheduler and health consult it). Recovery is the
    same setter with the healthy value; each row below is asserted with its
    recovery in ``tests/supervisor/test_degraded.py``.
    """

    #: LLM (x.ai) reachable; False degrades bot-08-signal.
    llm_available: bool = True
    #: signal.require_llm: when True the desk is observe-only for new buys
    #: while the LLM is down; otherwise rule-based scoring in live-paper.
    require_llm: bool = False
    #: RPC endpoints in failover order; False entries are down.
    rpc_endpoints: list[bool] = field(default_factory=lambda: [True])
    #: PumpPortal WS last frame (virtual ts), None when never connected.
    ws_last_frame_at: float | None = None
    #: Ledger writable; False buffers orders up to LEDGER_BUFFER_CAP.
    ledger_writable: bool = True
    #: Buffered order rows while the ledger is unwritable, in order.
    ledger_buffer: list[dict[str, Any]] = field(default_factory=list)
    #: persistence_down escalation already raised for the current outage.
    persistence_raised: bool = False

    # -- LLM (paper-engine.md 6.7 row 1) ---------------------------------
    def signal_scoring_mode(self, *, replay: bool) -> str:
        """``llm`` | ``rule_fallback`` | ``observe_only_buys`` | ``replay``."""
        if replay:
            return "replay"
        if self.llm_available:
            return "llm"
        if self.require_llm:
            return "observe_only_buys"
        return "rule_fallback"

    # -- RPC (paper-engine.md 6.7 row 2) ----------------------------------
    @property
    def rpc_blind(self) -> bool:
        """True after every failover endpoint fails."""
        return bool(self.rpc_endpoints) and not any(self.rpc_endpoints)

    def note_rpc_result(self, index: int, ok: bool) -> None:
        """Record one endpoint probe; healthy probes recover BLIND."""
        if 0 <= index < len(self.rpc_endpoints):
            self.rpc_endpoints[index] = ok

    # -- WS (paper-engine.md 6.7 rows 3-4) --------------------------------
    def note_ws_frame(self, at: float) -> None:
        """Fresh PumpPortal frame; recovers DataStale."""
        self.ws_last_frame_at = at

    def ws_data_stale(self, now: float) -> bool:
        """DataStale trips after 120 s of WS silence."""
        if self.ws_last_frame_at is None:
            return False
        return now - self.ws_last_frame_at > WS_STALE_S

    # -- ledger (paper-engine.md 6.7 row: unwritable) ----------------------
    def buffer_order(self, row: Mapping[str, Any]) -> None:
        """Buffer one refused order; raises past the 1000-event bound."""
        if len(self.ledger_buffer) >= LEDGER_BUFFER_CAP:
            raise LedgerUnavailable("order buffer full (1000 events)")
        self.ledger_buffer.append(dict(row))

    def drain_buffer(self, store: LedgerStore) -> int:
        """Append buffered rows in order after recovery; returns count."""
        count = 0
        while self.ledger_buffer:
            row = self.ledger_buffer.pop(0)
            store.append(
                ts_utc=str(row["ts_utc"]),
                source=str(row["source"]),
                correlation_id=str(row["correlation_id"]),
                idempotency_key=str(row["idempotency_key"]),
                type=str(row["type"]),
                payload=row["payload"],
            )
            count += 1
        self.persistence_raised = False
        return count

    # -- clock skew (paper-engine.md 6.7 row: skew) -------------------------
    @staticmethod
    def skew_detected(now: float, head_ts: float) -> bool:
        """True when the clock trails the ledger head beyond 5 s."""
        return now < head_ts - CLOCK_SKEW_S


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
    ) -> None:
        unknown = set(cycles) - set(ROSTER)
        if unknown:
            raise ValueError(f"unknown seats in cycle map: {sorted(unknown)}")
        missing = [seat for seat in ROSTER if seat not in cycles]
        if missing:
            raise ValueError(f"cycle map missing seats: {missing}")
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
        self.tasks: dict[str, SeatTask] = {
            seat: SeatTask(
                seat,
                (seat_cadences or {}).get(seat, SEAT_CADENCES[seat]),
                cycles[seat],
                clock=clock,
                rng=rng,
                store=store,
                source=source,
                correlation_id=correlation_id,
                notifier=notifier,
                observe_only=self.observe_only,
                cycle_observer=cycle_observer,
                stale_cadence_s=SEAT_CADENCES[seat],
            )
            for seat in ROSTER
        }
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
        """Ledger-recorded level; live mode always forces manual-ticket."""
        if self._mode == "live":
            return "manual-ticket"
        try:
            return read_autonomy(self._store)
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

    def _start_due(self) -> dict[str, str]:
        """Start each due seat as its own task, in roster order, without awaiting it.

        A seat whose previous cycle is still running is reported ``"busy"`` and
        not started again, so one seat never overlaps itself.
        """
        now = self._clock.now()
        outcomes: dict[str, str] = {}
        for seat in ROSTER:
            if not self.tasks[seat].is_due(now):
                continue
            running = self._inflight.get(seat)
            if running is not None and not running.done():
                outcomes[seat] = "busy"
                continue
            child = asyncio.ensure_future(self.tasks[seat].run_guarded(self._seat_context(seat)))
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
            if not self.tasks[seat].is_due(self._clock.now()):
                continue  # not due this tick: no outcome is reported, as before
            child = asyncio.ensure_future(self.tasks[seat].run_guarded(self._seat_context(seat)))
            self._inflight[seat] = child
            try:
                outcomes[seat] = await child
            except asyncio.CancelledError:
                child.cancel()
                raise
            finally:
                self._inflight.pop(seat, None)
        await self._end_of_tick(heartbeats=heartbeats)
        return outcomes

    async def run_once(self) -> dict[str, str]:
        """One full cycle of all ten seats in roster order (AUTO-006)."""
        self._emit_rollover(self._clock.now())
        outcomes: dict[str, str] = {}
        for seat in ROSTER:
            task = self.tasks[seat]
            child = asyncio.ensure_future(task.run_guarded(self._seat_context(seat)))
            self._inflight[seat] = child
            try:
                outcomes[seat] = await child
            except asyncio.CancelledError:
                child.cancel()
                raise
        # A one-shot cycle runs each seat once; cadence heartbeats apply to the serve loop.
        await self._end_of_tick(heartbeats=False)
        return outcomes

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
            for seat in ROSTER:
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
        for event in events:
            state = reduce(state, event)
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
        """Readyz: ledger CONSISTENT and every seat completed one cycle."""
        try:
            consistent = bool(self._store.verify())
        except Exception:
            return False
        return consistent and all(task.cycles >= 1 for task in self.tasks.values())

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


def _replay_cycles(
    *,
    clock: Clock,
    rng: Any,
    store: LedgerStore,
    risk: Any,
    degraded: DegradedState,
    dataset_events: list[dict[str, Any]],
    replay_llm: Any | None,
    dataset_name: str,
    filter_cfg: Any,
    trading: _ReplayTrading | None = None,
) -> dict[str, Callable[[SeatContext], Awaitable[Mapping[str, Any] | None]]]:
    """The ten offline seat cycles for ``--once --replay`` (AUTO-006).

    Without ``trading`` every cycle is read-only against the replay ledger: the
    sniper evaluates one risk check and places nothing (the serve path). With
    ``trading`` the sniper places each BUY candidate through its granted
    ``exec.place`` tool, and risk plus PaperAdapter approve or veto each one.
    Other seats stay read-only, and the journal fold is already on the ledger.
    """

    async def _chief(ctx: SeatContext) -> dict[str, Any]:
        return {"autonomy": ctx.autonomy_level}

    async def _scout(ctx: SeatContext) -> dict[str, Any]:
        return {"candidates": len(dataset_events)}

    async def _mark_open() -> None:
        """Refresh every open position's mark (no-op without a trading wiring)."""
        if trading is not None and trading.refresh_marks is not None:
            await trading.refresh_marks()

    async def _risk(ctx: SeatContext) -> dict[str, Any]:
        await _mark_open()
        verdict = risk.evaluate_halts(source="replay", correlation_id=ctx.correlation_id)
        return {"halt": verdict}

    async def _whale(ctx: SeatContext) -> dict[str, Any]:
        return {"blind": degraded.rpc_blind}

    async def _sniper(ctx: SeatContext) -> dict[str, Any]:
        if ctx.observe_only or not dataset_events:
            return {"orders": 0, "observe_only": ctx.observe_only}
        await _mark_open()
        if trading is not None:
            return await _place_candidates(trading)
        first = dataset_events[0]
        mint = str(first.get("mint", ""))
        if len(mint) < 32:
            return {"orders": 0, "reason": "no_mint"}
        factory = IdFactory(clock, rng)
        with bind_seat("bot-04-sniper"):
            order = OrderRequest(
                ticket_id="SOL-20260101-001",
                mint=mint,
                side=Side.BUY,
                decision_id=factory.ulid(),
                size_lamports=10_000_000,
                max_slippage_bps=100,
                approval_id=f"apr-{factory.ulid()}",
                correlation_id=str(ctx.correlation_id),
            )
            decision = risk.check(order, seat="bot-04-sniper", source="replay")
        return {"orders": 0, "risk_reason": decision.reason}

    async def _rug(ctx: SeatContext) -> dict[str, Any]:
        if degraded.rpc_blind:
            return {"verdict": "BLIND"}
        return {"verdict": "CLEAR"}

    async def _exit(ctx: SeatContext) -> dict[str, Any]:
        opened = [e for e in store.read(limit=None) if e.get("type") == "PositionOpened"]
        if trading is None or ctx.observe_only:
            return {"open": len(opened), "rule_sells": 0}
        sold = await _run_exit_rules(trading)
        return {"open": len(opened), "rule_sells": len(sold)}

    async def _shill(ctx: SeatContext) -> dict[str, Any]:
        return {"leads": 0}

    async def _signal(ctx: SeatContext) -> dict[str, Any]:
        if replay_llm is None:
            return {"scoring": "skipped"}
        # Recorded latency is virtual time: only a FixtureClock advances. Under the
        # wall clock it lands on a scratch timeline, never on host time.
        if isinstance(clock, FixtureClock):
            latency_clock = clock
        else:
            latency_clock = FixtureClock(start=clock.now())
        request = llm_request_for(dataset_name, list(dataset_events))
        outcome = replay_llm.complete(request, latency_clock)
        return {"scoring": "llm", "outcome": outcome.outcome}

    async def _journal(ctx: SeatContext) -> dict[str, Any]:
        await _mark_open()
        decision = decide_replay(list(dataset_events), filter_cfg)
        return {"decision": decision.decision, "reason": decision.reason}

    return {
        "bot-00-chief": _chief,
        "bot-01-scout": _scout,
        "bot-02-risk": _risk,
        "bot-03-whale": _whale,
        "bot-04-sniper": _sniper,
        "bot-05-rug": _rug,
        "bot-06-exit": _exit,
        "bot-07-shill": _shill,
        "bot-08-signal": _signal,
        "bot-09-journal": _journal,
    }


def dataset_events_start(dataset: Any) -> float:
    """First fixture stamp for the replay clock."""
    stamps = [event_epoch(event) for event in dataset.events]
    return min(stamps) if stamps else 0.0


def dataset_stamps(dataset: Any) -> list[float]:
    """Sorted, distinct epoch stamps of the recording: the replay timeline, in order."""
    return sorted({event_epoch(event) for event in dataset.events})


REPLAY_TICKET = "SOL-20260101-001"
REPLAY_BUY_LAMPORTS = 10_000_000
REPLAY_SLIPPAGE_BPS = 100
DEFAULT_ROSTER_DIR = Path(__file__).resolve().parents[3] / "contracts" / "tool-rosters"
#: The only seat that sells on exit rules (TOOL-009, PAPER-007).
EXIT_SEAT = "bot-06-exit"
#: Row types an order attempt writes. Only the sniper's granted trades add them.
TRADE_ROW_TYPES = frozenset(
    {
        "ApprovalRecorded",
        "FillRecorded",
        "OrderPlaced",
        "OrderRejected",
        "PositionClosed",
        "PositionOpened",
    }
)
#: Risk rows a replay cycle can legitimately produce under the selected settings: a
#: daily-loss or drawdown halt (``HaltSet``), a tripped breaker, and the position marks
#: the journal and risk seats refresh (``MarkToMarket``). Anything else is refused.
RISK_ROW_TYPES = frozenset({"HaltSet", "BreakerTripped", "MarkToMarket"})
_VIRTUAL_STEP_S = 0.25
_VIRTUAL_MAX_STEPS = 4000
#: Real seconds between recorded steps when a serve replays its fixture timeline.
SERVE_PACE_S = 1.0
#: Fixture supervisors check the sniper and exit seats on every recorded tick. The recording
#: is their poll schedule, so the seat cadence (a live-host poll rate) does not gate them.
FIXTURE_SEAT_CADENCES: dict[str, float] = {"bot-04-sniper": 0.0, "bot-06-exit": 0.0}


@dataclass
class _ReplayTrading:
    """Sniper wiring for one replay cycle: the granted place tool and the candidates."""

    clock: Clock
    ids: IdFactory
    place: Tool
    candidates: Sequence[CandidateVerdict]
    attempts: list[ReplayTrade] = field(default_factory=list)
    attempted: set[int] = field(default_factory=set)
    exit_place: Tool | None = None
    exits: ExitRules | None = None
    refresh_marks: Callable[[], Awaitable[None]] | None = None


@dataclass
class ReplayRuntime:
    """One offline replay sandbox: ledger, virtual clock, risk, paper adapter, registry."""

    dataset: FixtureDataset
    ledger_path: Path
    store: LedgerStore
    clock: Clock
    ids: IdFactory
    risk: RiskEngine
    adapter: PaperAdapter
    registry: ToolRegistry
    manifests: dict[str, BotManifest]
    candidates: list[CandidateVerdict]
    curves: FixtureCurveSource
    exits: ExitsSettings


def open_replay_runtime(
    dataset_dir: str | Path,
    filter_cfg: Any,
    *,
    seed: int,
    ledger_path: str | Path | None = None,
    roster_dir: str | Path | None = None,
    clock: Clock | None = None,
    exits: ExitsSettings | None = None,
    budget: RiskBudget | None = None,
    limits: EngineLimits | None = None,
) -> ReplayRuntime:
    """Open one offline replay sandbox over the dataset's ledger (G1, G7).

    Replay is hermetic: live-host kill state is never read (empty env, no kill
    file), curve reads and reserves come from the fixture ticks at virtual time,
    and the registry holds only the replay's ``exec.place`` and
    ``risk.kill_switch`` tools. A seat reaches them only through its roster
    grant. The sandbox runs under ``autonomous-paper``: a buy under
    ``manual-ticket`` needs a human approval that a replay never has. Risk still
    checks every order.
    """
    dataset = load_dataset(Path(dataset_dir))
    target = (
        Path(ledger_path)
        if ledger_path is not None
        else REPLAY_ROOT / dataset.manifest.dataset / "ledger.sqlite"
    )
    clock = clock if clock is not None else FixtureClock(start=dataset_events_start(dataset))
    rng = make_rng(seed)
    ids = IdFactory(clock, rng)
    budget = budget if budget is not None else RiskBudget()
    limits = limits if limits is not None else EngineLimits()
    store = LedgerStore(str(target))
    try:
        store.set_meta("initial_equity_lamports", str(budget.paper_equity_lamports))
        curves = FixtureCurveSource(dataset, clock)
        risk = RiskEngine(
            store=store,
            budget=budget,
            ids=IdFactory(clock, rng),
            clock=clock,
            limits=limits,
            autonomy="autonomous-paper",
            # Replay is hermetic: live-host kill state (env/file/alert) must
            # not leak rows into the deterministic ledger.
            env={},
            get_reserves=curves.reserves,
        )
        adapter = PaperAdapter(
            store=store,
            risk=risk,
            ids=IdFactory(clock, rng),
            clock=clock,
            rng=make_rng(seed),
            budget=budget,
            limits=limits,
            price_source=curves,
            # The fixture is the venue: no random tx drop, so a recorded buy fills.
            p_drop=0.0,
            source="replay",
        )
        registry, _audits = build_registry(clock=clock, rng=make_rng(seed))
        registry.register(build_place_tool(adapter, lambda: budget, clock))
        registry.register(
            build_kill_switch_tool(
                store,
                clock,
                None,
                close_position=adapter.close_position,
                barrier=adapter.inflight_barrier,
            )
        )
        roster = Path(roster_dir) if roster_dir is not None else DEFAULT_ROSTER_DIR
        candidates = evaluate_candidates(dataset.events, filter_cfg)
    except BaseException:
        store.close()
        raise
    return ReplayRuntime(
        dataset=dataset,
        ledger_path=target,
        store=store,
        clock=clock,
        ids=ids,
        risk=risk,
        adapter=adapter,
        registry=registry,
        manifests=load_bot_manifests(roster),
        candidates=candidates,
        curves=curves,
        exits=exits if exits is not None else ExitsSettings(),
    )


async def _settle_on_virtual_time(clock: FixtureClock, awaitable: Awaitable[Any]) -> Any:
    """Await one tool call while virtual time advances, so its confirmation latency elapses.

    The paper adapter sleeps its seeded confirmation latency on the fixture clock,
    which moves only when advanced. A call that never settles within the bound
    fails loudly instead of spinning.
    """
    task = asyncio.ensure_future(awaitable)
    steps = 0
    while not task.done():
        if steps >= _VIRTUAL_MAX_STEPS:
            task.cancel()
            raise RuntimeError("replay order did not settle on virtual time")
        clock.advance_to(clock.now() + _VIRTUAL_STEP_S)
        steps += 1
        await clock.yield_to_loop()
    return task.result()


async def _await_order(clock: Clock, awaitable: Awaitable[Any]) -> Any:
    """Settle one order: virtual time advances on a fixture clock; a live clock awaits directly."""
    if isinstance(clock, FixtureClock):
        return await _settle_on_virtual_time(clock, awaitable)
    return await awaitable


async def _place_candidates(trading: _ReplayTrading) -> dict[str, Any]:
    """Place each BUY candidate once, when the recorded timeline reaches its tick.

    A candidate waits until the clock is at or past its own tick, and is never priced
    from a later one. The tool resolves through the sniper's roster grant, so risk and
    PaperAdapter approve or veto each order, and the attempt with its outcome is recorded.
    """
    for index, candidate in enumerate(trading.candidates):
        if candidate.verdict.decision != BUY or index in trading.attempted:
            continue
        if candidate.ts > trading.clock.now():
            continue  # the recording has not reached this candidate yet
        trading.attempted.add(index)
        if trading.refresh_marks is not None:
            await trading.refresh_marks()
        mint = candidate.token.mint
        payload = trading.place.spec.input_model.model_validate(
            {
                "ticket_id": REPLAY_TICKET,
                "mint": mint,
                "side": "buy",
                "decision_id": trading.ids.ulid(),
                "size_lamports": REPLAY_BUY_LAMPORTS,
                "max_slippage_bps": REPLAY_SLIPPAGE_BPS,
                "approval_id": f"apr-{trading.ids.ulid()}",
            }
        )
        with bind_seat("bot-04-sniper"), bind_correlation(CorrelationId.new(trading.ids)):
            settled = await _await_order(trading.clock, trading.place(payload))
        result = settled.model_dump(mode="json")
        outcome = str(result["status"])
        reason = str(result["reason"] or ("ok" if outcome == "filled" else ""))
        trading.attempts.append(ReplayTrade(side="buy", mint=mint, outcome=outcome, reason=reason))
    return {"orders": len(trading.attempts)}


def _check_cycle_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    """Only day-keyed ``DailyRollover`` rows and the sniper's order rows may be new."""
    for row in rows:
        row_type = row.get("type")
        if row_type == "DailyRollover":
            day = str((row.get("payload") or {}).get("day_utc", ""))
            if not day or row.get("idempotency_key") != rollover_key(day):
                raise RuntimeError("replay seat cycles wrote an unkeyed DailyRollover")
        elif row_type in TRADE_ROW_TYPES or row_type in RISK_ROW_TYPES:
            continue
        elif row_type == "Escalation" and (row.get("payload") or {}).get("kind") == "graduated":
            continue  # the exit seat closed a graduated position (exit_rules._close_graduated)
        else:
            raise RuntimeError(f"replay seat cycles wrote an unexpected {row_type} row")


async def _place_rule_sell(
    trading: _ReplayTrading, mint: str, ticket: str, units: int, rule: str
) -> dict[str, Any]:
    """Submit one rule sell through the exit seat's granted ``exec.place`` (TOOL-009)."""
    if trading.exit_place is None:
        raise RuntimeError("exit seat has no granted exec.place")
    payload = trading.exit_place.spec.input_model.model_validate(
        {
            "ticket_id": ticket,
            "mint": mint,
            "side": "sell",
            "decision_id": trading.ids.ulid(),
            "token_units": units,
            "max_slippage_bps": REPLAY_SLIPPAGE_BPS,
            "approval_id": f"apr-{trading.ids.ulid()}",
            "exit_reason": rule,
        }
    )
    with bind_seat(EXIT_SEAT), bind_correlation(CorrelationId.new(trading.ids)):
        settled = await _await_order(trading.clock, trading.exit_place(payload))
    result: dict[str, Any] = settled.model_dump(mode="json")
    outcome = str(result["status"])
    reason = str(result["reason"] or ("ok" if outcome == "filled" else ""))
    trading.attempts.append(
        ReplayTrade(side="sell", mint=mint, outcome=outcome, reason=reason, rule=rule)
    )
    return result


async def _run_exit_rules(trading: _ReplayTrading) -> list[RuleSell]:
    """One exit pass at the current clock: the rules see the price as of this tick."""
    if trading.exits is None:
        return []
    return await trading.exits.check(trading.clock.now())


def _replay_trading(runtime: ReplayRuntime) -> _ReplayTrading:
    """Resolve the sniper's and the exit seat's ``exec.place`` through their roster grants.

    Each grant is resolved through the registry, so a seat without one cannot place. The
    exit seat sells only through its own grant, and only on a rule that fired.
    """
    with bind_correlation(CorrelationId.new(runtime.ids)):
        place = runtime.registry.find(
            "exec.place",
            max_side_effect=SideEffect.PAPER_WRITE,
            bot=runtime.manifests["bot-04-sniper"],
        )
        exit_place = runtime.registry.find(
            "exec.place",
            max_side_effect=SideEffect.PAPER_WRITE,
            bot=runtime.manifests[EXIT_SEAT],
        )

    async def refresh_marks() -> None:
        """Write one combined mark for every held mint at this instant.

        A position without a fresh mark is refused as data_stale and counts as zero value in
        loss checks, so the replay refreshes marks before risk checks and before each order.
        Each mint keeps the recorded time of its own tick, so a silent mint stays visibly old.
        """
        await runtime.adapter.mark_open_positions(source="replay")

    trading = _ReplayTrading(
        clock=runtime.clock,
        ids=runtime.ids,
        place=place,
        candidates=runtime.candidates,
        exit_place=exit_place,
        refresh_marks=refresh_marks,
    )

    async def place_sell(mint: str, ticket: str, units: int, rule: str) -> dict[str, Any]:
        return await _place_rule_sell(trading, mint, ticket, units, rule)

    async def close_graduated(mint: str, last_s: int, last_t: int) -> dict[str, Any] | None:
        """Close a graduated position at its last open reserves; book it as a trade."""
        with bind_seat(EXIT_SEAT):
            row = await runtime.adapter.close_on_graduation(
                mint, last_s=last_s, last_t=last_t, source="replay"
            )
        if row is not None:
            trading.attempts.append(
                ReplayTrade(side="sell", mint=mint, outcome="filled", reason="ok", rule="graduated")
            )
        return row

    trading.exits = ExitRules(
        store=runtime.store,
        curves=runtime.curves,
        exits=runtime.exits,
        clock=runtime.clock,
        place_sell=place_sell,
        graduate=close_graduated,
    )
    return trading


def run_once_replay(
    dataset_dir: str | Path,
    filter_cfg: Any,
    *,
    seed: int,
    ledger_path: str | Path | None = None,
    health_path: str | Path | None = None,
    roster_dir: str | Path | None = None,
    exits: ExitsSettings | None = None,
    budget: RiskBudget | None = None,
    limits: EngineLimits | None = None,
) -> ReplayResult:
    """AUTO-006: replay verdict, then one full recorded timeline, offline.

    ``run_replay`` writes the checkpoint verdict row first, so the stdout line and
    ``cycle_end`` log are unchanged. The seats then run tick by tick along the recorded
    timeline (:func:`serve_fixture_timeline`), so each BUY is judged and priced at its own
    tick and an exit rule sees every later tick in order. The sniper places BUYs and the
    exit seat sells through their granted ``exec.place``, so risk and PaperAdapter approve
    or veto each order. The result lists each attempt, the final ledger sequence, and the
    hash of the completed, verified chain.
    """
    result = run_replay(dataset_dir, filter_cfg, seed=seed, ledger_path=ledger_path)
    runtime = open_replay_runtime(
        dataset_dir,
        filter_cfg,
        seed=seed,
        ledger_path=ledger_path,
        roster_dir=roster_dir,
        exits=exits,
        budget=budget,
        limits=limits,
    )
    try:
        trading = _replay_trading(runtime)
        rng = make_rng(seed)
        degraded = DegradedState()
        cycles = _replay_cycles(
            clock=runtime.clock,
            rng=rng,
            store=runtime.store,
            risk=runtime.risk,
            degraded=degraded,
            dataset_events=list(runtime.dataset.events),
            replay_llm=load_llm_records(Path(dataset_dir)),
            dataset_name=runtime.dataset.manifest.dataset,
            filter_cfg=filter_cfg,
            trading=trading,
        )
        supervisor = Supervisor(
            store=runtime.store,
            clock=runtime.clock,
            rng=rng,
            cycles=cycles,
            mode="paper",
            source="replay",
            correlation_id="desk",
            notifier=None,
            degraded=degraded,
            health_path=health_path,
            risk=runtime.risk,
            budget=budget,
            seat_cadences=FIXTURE_SEAT_CADENCES,
        )
        before = runtime.store.count()
        ticks = asyncio.run(
            serve_fixture_timeline(
                supervisor, dataset_stamps(runtime.dataset), hold=False, heartbeats=False
            )
        )
        for outcome in ticks:
            for seat in ROSTER:
                if outcome.get(seat) == "crash":
                    raise RuntimeError(f"seat {seat} cycle crashed")
        _check_cycle_rows(runtime.store.read(limit=None)[before:])
        if not supervisor.ready():
            raise RuntimeError("supervisor not ready after the recorded timeline")
        if not runtime.store.verify():
            raise LedgerInconsistent("replay ledger failed verification after the cycle")
        final_seq = int(runtime.store.read(limit=None)[-1]["seq"])
        events_hash = ledger_events_hash(runtime.ledger_path)
    finally:
        runtime.store.close()
    return replace(
        result,
        seq=final_seq,
        events_hash=events_hash,
        trades=tuple(trading.attempts),
    )


async def serve_fixture_timeline(
    supervisor: Supervisor,
    stamps: Sequence[float],
    *,
    pace: Clock | None = None,
    pace_s: float = 0.0,
    hold: bool = False,
    heartbeats: bool = True,
) -> list[dict[str, str]]:
    """Advance the fixture clock along the recording and tick the supervisor at each tick.

    Each recorded tick is one supervisor tick at its own time, so a BUY is judged and
    priced at its own tick and an exit rule sees every later tick in order. A tick the
    clock has already passed (an order's latency moved it on) is skipped, never replayed
    backwards. With ``hold`` the clock then keeps stepping at the tick cadence until the
    supervisor is stopped, so a serve stays up after its recording ends. ``pace_s`` real
    seconds separate steps (zero for a one-shot run), waited on the injected ``pace`` clock
    (a ``WallClock`` in serve, so production keeps real time; never ``asyncio.sleep``).
    Returns each recorded tick's outcomes.
    """
    clock = supervisor.clock
    if not isinstance(clock, FixtureClock):
        raise RuntimeError("a fixture timeline needs the fixture clock")
    ticks: list[dict[str, str]] = []
    for at in stamps:
        if at < clock.now():
            continue
        clock.advance_to(at)
        ticks.append(await supervisor.tick_once(heartbeats=heartbeats))
        if pace_s > 0 and pace is not None:
            await pace.sleep(pace_s)
        if supervisor.stopped:
            return ticks
    if not hold:
        return ticks
    while not supervisor.stopped:
        clock.advance_to(clock.now() + TICK_S)
        await supervisor.tick_once(heartbeats=heartbeats)
        if pace_s > 0 and pace is not None:
            await pace.sleep(pace_s)
    return ticks


def build_serve_replay(
    dataset_dir: str | Path,
    filter_cfg: Any,
    *,
    seed: int,
    clock: Clock | None = None,
    ledger_path: str | Path | None = None,
    health_path: str | Path | None = None,
    exits: ExitsSettings | None = None,
    budget: RiskBudget | None = None,
    limits: EngineLimits | None = None,
) -> tuple[Supervisor, Metrics, LedgerStore]:
    """Construct the D1 serve supervisor over a replayed ledger.

    Runs ``run_replay`` once to rebuild the ledger, then wires the ten
    offline seat cycles from ``_replay_cycles`` with ``source="replay"`` so
    the health body carries ``ledger_source=replay`` (never live data). The
    returned store stays open; the caller closes it after the serve loop.
    """
    run_replay(dataset_dir, filter_cfg, seed=seed, ledger_path=ledger_path)
    runtime = open_replay_runtime(
        dataset_dir,
        filter_cfg,
        seed=seed,
        ledger_path=ledger_path,
        clock=clock,
        exits=exits,
        budget=budget,
        limits=limits,
    )
    store = runtime.store
    try:
        trading = _replay_trading(runtime)
        degraded = DegradedState()
        cycles = _replay_cycles(
            clock=runtime.clock,
            rng=make_rng(seed),
            store=store,
            risk=runtime.risk,
            degraded=degraded,
            dataset_events=list(runtime.dataset.events),
            replay_llm=load_llm_records(Path(dataset_dir)),
            dataset_name=runtime.dataset.manifest.dataset,
            filter_cfg=filter_cfg,
            trading=trading,
        )

        def _snapshot() -> dict[str, Any]:
            """Scrape-time gauges: ledger_seq is real; kill switch matches the health body."""
            try:
                seq = store.count()
            except Exception:
                seq = 0
            return {"ledger_seq": seq, "kill_switch": kill_switch_engaged(store)}

        metrics = Metrics(snapshot=_snapshot)
        supervisor = Supervisor(
            store=store,
            clock=runtime.clock,
            rng=make_rng(seed),
            cycles=cycles,
            mode="paper",
            source="replay",
            correlation_id="desk",
            notifier=None,
            degraded=degraded,
            health_path=health_path,
            risk=runtime.risk,
            budget=budget,
            cycle_observer=metrics.observe,
            seat_cadences=FIXTURE_SEAT_CADENCES,
        )
    except Exception:
        store.close()
        raise
    return supervisor, metrics, store


async def _finish_serve(
    supervisor: Supervisor,
    server: HealthServer,
    store: LedgerStore,
    health_path: str | Path | None,
) -> None:
    """Stop-time order: drain and write the final exports, then close server and store.

    ``shutdown`` drains running cycles, writes the ledger snapshot, flushes the
    JSONL export, and writes ``health.json`` with ``status=stopped`` while the
    store is still open. Without ``health_path`` the stopped body lands beside
    the ledger, next to the export files.
    """
    root = store.path.parent
    try:
        await shutdown(
            supervisor,
            store=store,
            health_path=str(health_path if health_path is not None else root / "health.json"),
            journal_dir=str(root / "journal"),
            trades_path=str(root / "trades.jsonl"),
        )
    except Exception as exc:
        log.warning("serve shutdown failed: %s", exc)
    finally:
        with contextlib.suppress(Exception):
            await server.stop()
        with contextlib.suppress(Exception):
            store.close()


async def serve_replay(
    dataset_dir: str | Path,
    filter_cfg: Any,
    *,
    seed: int,
    port: int,
    host: str = "127.0.0.1",
    ledger_path: str | Path | None = None,
    health_path: str | Path | None = None,
    exits: ExitsSettings | None = None,
    budget: RiskBudget | None = None,
    limits: EngineLimits | None = None,
    pace_s: float = SERVE_PACE_S,
) -> int:
    """D1 serve path: replay a recorded dataset in a loop, serving /healthz and /metrics.

    Binds ``host`` (loopback by default, so direct host runs never expose the
    read-only endpoints to the LAN). The container sets the host to 0.0.0.0
    through explicit configuration (PUMPGROK_HEALTH__HOST via compose) because
    Docker forwards published ports to the container IP, never to its loopback.
    LAN safety for the container comes from the compose file, which publishes
    127.0.0.1:8080 only; there are no unauthenticated write routes.
    SIGINT/SIGTERM stop the loop and the server closes before the store does.
    Fixture time follows the recording (see :func:`serve_fixture_timeline`), paced
    ``pace_s`` real seconds per step; after the last recorded tick the clock keeps
    moving at the tick cadence until stop. Returns 0.
    """
    supervisor, metrics, store = build_serve_replay(
        dataset_dir,
        filter_cfg,
        seed=seed,
        ledger_path=ledger_path,
        health_path=health_path,
        exits=exits,
        budget=budget,
        limits=limits,
    )
    server = HealthServer(
        supervisor.clock,
        supervisor.health_status,
        supervisor.ready,
        get_metrics=metrics.exposition,
    )
    bound = await server.start(host, port)
    log.info("serve listening on %s:%d (ledger_source=replay)", host, bound)
    install_signal_handlers(supervisor.request_stop)
    try:
        await serve_fixture_timeline(
            supervisor,
            dataset_stamps(load_dataset(Path(dataset_dir))),
            pace=WallClock(),
            pace_s=pace_s,
            hold=True,
        )
        return 0
    finally:
        await _finish_serve(supervisor, server, store, health_path)
