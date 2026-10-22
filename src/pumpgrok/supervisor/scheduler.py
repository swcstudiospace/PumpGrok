"""Ten-seat supervised scheduler (paper-engine.md 6.1-6.2, 6.7).

Within one supervisor tick (``TICK_S = 1`` s) due seats start in roster
order (00..09) so replay ordering is stable. Each seat runs its cycle in
its own ``asyncio.Task`` under ``clock.timeout(seat_timeout)``; a timed-out
cycle counts as a crash. Every wait goes through the injected clock.

AUTO-005 degraded modes live here as :class:`DegradedState`: LLM fallback,
RPC failover/BLIND, WS reconnect/DataStale, bounded unwritable-ledger
buffer, and clock-skew refusal. AUTO-006 is :func:`run_once_replay`: one
full ten-seat cycle over a fixture through the engine, risk, and paper
adapter, writing ``var/replay/<dataset>/ledger.sqlite`` with no network.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
import sqlite3
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.ids import Clock, IdFactory
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.engine.pipeline import decide_replay
from pumpgrok.ledger.autonomy import read_autonomy
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.logging.json import bind_seat
from pumpgrok.replay.clock import FixtureClock, WallClock, format_ts_utc, parse_ts_utc
from pumpgrok.replay.fixtures import event_epoch, load_dataset
from pumpgrok.replay.recorder import load_llm_records
from pumpgrok.replay.rng import make_rng
from pumpgrok.replay.runner import REPLAY_ROOT, llm_request_for, run_replay
from pumpgrok.risk.engine import RiskEngine, utc_day
from pumpgrok.risk.killswitch import env_engaged
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.supervisor.health import (
    HEALTH_FILE_INTERVAL_S,
    HealthServer,
    build_status,
    write_health_json,
)
from pumpgrok.supervisor.lifecycle import install_signal_handlers
from pumpgrok.supervisor.metrics import Metrics
from pumpgrok.supervisor.seat_task import (
    CLOCK_SKEW_S,
    ClockSkew,
    ObserveOnly,
    SeatContext,
    SeatTask,
    relay_tail,
)

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
        cycle_observer: Callable[[str, float, str], None] | None = None,
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
        self.observe_only = ObserveOnly()
        self.tasks: dict[str, SeatTask] = {
            seat: SeatTask(
                seat,
                SEAT_CADENCES[seat],
                cycles[seat],
                clock=clock,
                rng=rng,
                store=store,
                source=source,
                correlation_id=correlation_id,
                notifier=notifier,
                observe_only=self.observe_only,
                cycle_observer=cycle_observer,
            )
            for seat in ROSTER
        }
        self._stop = asyncio.Event()
        self._relay_cursor = 0
        self._started_at = clock.now()
        self._last_health_write = 0.0
        self._last_rollover_day: str | None = None

    @property
    def clock(self) -> Clock:
        """Injected clock (lifecycle drains against it)."""
        return self._clock

    @property
    def degraded(self) -> DegradedState:
        """Live degraded-mode probes."""
        return self._degraded

    def running_tasks(self) -> list[asyncio.Task[Any]]:
        """Live seat tasks, excluding the caller (shutdown drain owns it)."""
        current = asyncio.current_task()
        return [t for t in asyncio.all_tasks() if t is not current and not t.done()]

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

    async def tick_once(self) -> dict[str, str]:
        """Start every due seat in roster order; returns seat -> outcome."""
        outcomes: dict[str, str] = {}
        for seat in ROSTER:
            task = self.tasks[seat]
            if not task.is_due(self._clock.now()):
                continue
            child = asyncio.ensure_future(task.run_guarded(self._seat_context(seat)))
            try:
                outcomes[seat] = await child
            except asyncio.CancelledError:
                child.cancel()
                raise
        await self._end_of_tick()
        return outcomes

    async def run_once(self) -> dict[str, str]:
        """One full cycle of all ten seats in roster order (AUTO-006)."""
        outcomes: dict[str, str] = {}
        for seat in ROSTER:
            task = self.tasks[seat]
            child = asyncio.ensure_future(task.run_guarded(self._seat_context(seat)))
            try:
                outcomes[seat] = await child
            except asyncio.CancelledError:
                child.cancel()
                raise
        await self._end_of_tick()
        return outcomes

    async def _end_of_tick(self) -> None:
        now = self._clock.now()
        resumed = self.observe_only.fold_resume(self._store)
        for seat in resumed:
            log.info("seat %s resumed from observe-only", seat)
        self._sync_risk_latch()
        for seat in ROSTER:
            await self.tasks[seat].check_stale(now)
        self._relay_cursor = await relay_tail(
            self._store, self._notifier, self._clock, self._relay_cursor
        )
        self._emit_rollover(now)
        healthy_interval = now - self._last_health_write >= HEALTH_FILE_INTERVAL_S
        if self._health_path is not None and healthy_interval:
            self._last_health_write = now
            try:
                write_health_json(str(self._health_path), self.health_status())
            except OSError as exc:
                log.warning("health.json write failed: %s", exc)

    def _emit_rollover(self, now: float) -> None:
        """Append one ``DailyRollover`` per UTC day, including the first day seen.

        Emitted here, outside the seat cycles: ``run_once_replay`` narrows its
        read-only assertion to allow exactly these day-keyed rows (5.2
        conflict), so seat cycles stay read-only while the ledger still
        records one rollover per UTC day (D6).
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
                    "day_start_equity_lamports": self._day_start_equity(),
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

    def _day_start_equity(self) -> int:
        """Day-start equity for the rollover row; 0 when the ledger is fresh."""
        try:
            meta = self._store.get_meta("initial_equity_lamports")
            return int(meta) if meta is not None else 0
        except Exception:
            return 0

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
        """Tick until stop; shutdown owns snapshot/export/health instead."""
        while not self._stop.is_set():
            await self.tick_once()
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
) -> dict[str, Callable[[SeatContext], Awaitable[Mapping[str, Any] | None]]]:
    """The ten offline seat cycles for ``--once --replay`` (AUTO-006).

    Every cycle is read-only against the replay ledger: the engine folds
    fixture ticks, risk evaluates the sniper order (expecting refusal on
    evidence-less candidates), and the adapter path stays simulate-only.
    The journal fold is already on the ledger (``run_replay`` ran first),
    so the cycle appends zero rows and the checkpoint ledger stays exact.
    """

    async def _chief(ctx: SeatContext) -> dict[str, Any]:
        return {"autonomy": ctx.autonomy_level}

    async def _scout(ctx: SeatContext) -> dict[str, Any]:
        return {"candidates": len(dataset_events)}

    async def _risk(ctx: SeatContext) -> dict[str, Any]:
        verdict = risk.evaluate_halts(source="replay", correlation_id=ctx.correlation_id)
        return {"halt": verdict}

    async def _whale(ctx: SeatContext) -> dict[str, Any]:
        return {"blind": degraded.rpc_blind}

    async def _sniper(ctx: SeatContext) -> dict[str, Any]:
        if ctx.observe_only or not dataset_events:
            return {"orders": 0, "observe_only": ctx.observe_only}
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
        return {"open": len(opened)}

    async def _shill(ctx: SeatContext) -> dict[str, Any]:
        return {"leads": 0}

    async def _signal(ctx: SeatContext) -> dict[str, Any]:
        if replay_llm is None:
            return {"scoring": "skipped"}
        outcome = replay_llm.complete(llm_request_for(dataset_name, list(dataset_events)), clock)
        return {"scoring": "llm", "outcome": outcome.outcome}

    async def _journal(ctx: SeatContext) -> dict[str, Any]:
        decision = decide_replay(list(dataset_events), filter_cfg, clock.now())
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


def run_once_replay(
    dataset_dir: str | Path,
    filter_cfg: Any,
    *,
    seed: int,
    ledger_path: str | Path | None = None,
    health_path: str | Path | None = None,
) -> Any:
    """AUTO-006: replay verdict plus one full ten-seat cycle, offline.

    Runs the existing ``run_replay`` first (the checkpoint verdict row,
    stdout line, and ``cycle_end`` log stay byte-identical), then executes
    all ten seat cycles in roster order through the engine, risk, and paper
    adapter against the same ledger. Seat cycles are read-only, so the
    ledger keeps exactly the verdict row.
    """
    result = run_replay(dataset_dir, filter_cfg, seed=seed, ledger_path=ledger_path)
    source_dir = Path(dataset_dir)
    dataset = load_dataset(source_dir)
    if ledger_path is not None:
        target = Path(ledger_path)
    else:
        target = REPLAY_ROOT / dataset.manifest.dataset / "ledger.sqlite"
    clock = FixtureClock(start=dataset_events_start(dataset))
    rng = make_rng(seed)
    store = LedgerStore(str(target))
    try:
        raw_autonomy = read_autonomy(store)
        if raw_autonomy == "autonomous-paper":
            autonomy_level: Literal["manual-ticket", "autonomous-paper"] = "autonomous-paper"
        else:
            autonomy_level = "manual-ticket"
        risk = RiskEngine(
            store=store,
            budget=RiskBudget(),
            ids=IdFactory(clock, rng),
            clock=clock,
            limits=EngineLimits(),
            autonomy=autonomy_level,
            # Replay is hermetic: live-host kill state (env/file/alert) must
            # not leak rows into the deterministic checkpoint ledger; ledger
            # KillSwitchSet rows are still honored through the store.
            env={},
        )
        degraded = DegradedState()
        replay_llm = load_llm_records(source_dir)
        cycles = _replay_cycles(
            clock=clock,
            rng=rng,
            store=store,
            risk=risk,
            degraded=degraded,
            dataset_events=list(dataset.events),
            replay_llm=replay_llm,
            dataset_name=dataset.manifest.dataset,
            filter_cfg=filter_cfg,
        )
        supervisor = Supervisor(
            store=store,
            clock=clock,
            rng=rng,
            cycles=cycles,
            mode="paper",
            source="replay",
            correlation_id="desk",
            notifier=None,
            degraded=degraded,
            health_path=health_path,
            risk=risk,
        )
        before = store.count()
        outcomes = asyncio.run(supervisor.run_once())
        after = store.count()
        for seat in ROSTER:
            if outcomes.get(seat) != "crash":
                continue
            raise RuntimeError(f"seat {seat} cycle crashed")
        if after != before:
            # 5.2 conflict resolved here (not in the seat cycles): seat cycles
            # stay read-only, but `_end_of_tick` emits the day-keyed
            # DailyRollover for the fixture day. Only those rows may appear.
            extra = store.read(limit=None)[before:]
            for row in extra:
                payload = row.get("payload") or {}
                day = str(payload.get("day_utc", ""))
                if row.get("type") != "DailyRollover" or not day:
                    raise RuntimeError(f"replay seat cycles must be read-only: {before} -> {after}")
                if row.get("idempotency_key") != rollover_key(day):
                    raise RuntimeError(f"replay seat cycles must be read-only: {before} -> {after}")
        if not supervisor.ready():
            raise RuntimeError("supervisor not ready after full cycle")
    finally:
        store.close()
    return result


def build_serve_replay(
    dataset_dir: str | Path,
    filter_cfg: Any,
    *,
    seed: int,
    clock: Clock | None = None,
    ledger_path: str | Path | None = None,
    health_path: str | Path | None = None,
) -> tuple[Supervisor, Metrics, LedgerStore]:
    """Construct the D1 serve supervisor over a replayed ledger.

    Runs ``run_replay`` once to rebuild the ledger, then wires the ten
    offline seat cycles from ``_replay_cycles`` with ``source="replay"`` so
    the health body carries ``ledger_source=replay`` (never live data). The
    returned store stays open; the caller closes it after the serve loop.
    """
    if clock is None:
        clock = WallClock()
    run_replay(dataset_dir, filter_cfg, seed=seed, ledger_path=ledger_path)
    source_dir = Path(dataset_dir)
    dataset = load_dataset(source_dir)
    if ledger_path is not None:
        target = Path(ledger_path)
    else:
        target = REPLAY_ROOT / dataset.manifest.dataset / "ledger.sqlite"
    rng = make_rng(seed)
    store = LedgerStore(str(target))
    try:
        raw_autonomy = read_autonomy(store)
        if raw_autonomy == "autonomous-paper":
            autonomy_level: Literal["manual-ticket", "autonomous-paper"] = "autonomous-paper"
        else:
            autonomy_level = "manual-ticket"
        risk = RiskEngine(
            store=store,
            budget=RiskBudget(),
            ids=IdFactory(clock, rng),
            clock=clock,
            limits=EngineLimits(),
            autonomy=autonomy_level,
            env={},
        )
        degraded = DegradedState()
        replay_llm = load_llm_records(source_dir)
        cycles = _replay_cycles(
            clock=clock,
            rng=rng,
            store=store,
            risk=risk,
            degraded=degraded,
            dataset_events=list(dataset.events),
            replay_llm=replay_llm,
            dataset_name=dataset.manifest.dataset,
            filter_cfg=filter_cfg,
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
            clock=clock,
            rng=rng,
            cycles=cycles,
            mode="paper",
            source="replay",
            correlation_id="desk",
            notifier=None,
            degraded=degraded,
            health_path=health_path,
            risk=risk,
            cycle_observer=metrics.observe,
        )
    except Exception:
        store.close()
        raise
    return supervisor, metrics, store


async def serve_replay(
    dataset_dir: str | Path,
    filter_cfg: Any,
    *,
    seed: int,
    port: int,
    host: str = "127.0.0.1",
    ledger_path: str | Path | None = None,
    health_path: str | Path | None = None,
) -> int:
    """D1 serve path: replay a recorded dataset in a loop, serving /healthz and /metrics.

    Binds ``host`` (loopback by default, so direct host runs never expose the
    read-only endpoints to the LAN). The container sets the host to 0.0.0.0
    through explicit configuration (PUMPGROK_HEALTH__HOST via compose) because
    Docker forwards published ports to the container IP, never to its loopback.
    LAN safety for the container comes from the compose file, which publishes
    127.0.0.1:8080 only; there are no unauthenticated write routes.
    SIGINT/SIGTERM stop the loop and the server closes before the store does.
    Returns 0.
    """
    supervisor, metrics, store = build_serve_replay(
        dataset_dir,
        filter_cfg,
        seed=seed,
        ledger_path=ledger_path,
        health_path=health_path,
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
        return await supervisor.serve_forever()
    finally:
        with contextlib.suppress(Exception):
            await server.stop()
        with contextlib.suppress(Exception):
            store.close()
