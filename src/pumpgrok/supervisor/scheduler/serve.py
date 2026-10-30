"""Replay entry points: one-shot verdicts and the fixture-timeline serve loop."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.core.ids import Clock
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.engine.pipeline import evaluate_candidates
from pumpgrok.ledger.active_set import load_verified_param_set, read_active_set
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore
from pumpgrok.replay.clock import FixtureClock, WallClock, parse_ts_utc
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.replay.recorder import load_llm_records
from pumpgrok.replay.rng import make_rng
from pumpgrok.replay.runner import ReplayResult, ledger_events_hash, run_replay
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.supervisor.health import HealthServer
from pumpgrok.supervisor.lifecycle import install_signal_handlers, shutdown
from pumpgrok.supervisor.metrics import Metrics
from pumpgrok.supervisor.scheduler.degraded import DegradedState, kill_switch_engaged
from pumpgrok.supervisor.scheduler.orders import _check_cycle_rows, _replay_trading
from pumpgrok.supervisor.scheduler.replay_cycles import _replay_cycles
from pumpgrok.supervisor.scheduler.replay_runtime import (
    FIXTURE_SEAT_CADENCES,
    SERVE_PACE_S,
    dataset_stamps,
    open_replay_runtime,
)
from pumpgrok.supervisor.scheduler.supervisor import ROSTER, TICK_S, Supervisor

if TYPE_CHECKING:
    from pumpgrok.supervisor.scheduler.replay_runtime import _ReplayTrading
    from pumpgrok.upgrade.params import ParamSet

log = logging.getLogger("pumpgrok.supervisor.scheduler")


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
    active_set: ParamSet | None = None,
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
    result = run_replay(
        dataset_dir, filter_cfg, seed=seed, ledger_path=ledger_path, active_set=active_set
    )
    runtime = open_replay_runtime(
        dataset_dir,
        filter_cfg,
        seed=seed,
        ledger_path=ledger_path,
        roster_dir=roster_dir,
        exits=exits,
        budget=budget,
        limits=limits,
        active_set=active_set,
    )
    try:
        trading = _replay_trading(runtime)
        rng = make_rng(seed)
        degraded = DegradedState()
        seat_filter = filter_cfg
        if active_set is not None:
            seat_filter = active_set.candidate().filter_settings()
        cycles = _replay_cycles(
            clock=runtime.clock,
            rng=rng,
            store=runtime.store,
            risk=runtime.risk,
            degraded=degraded,
            dataset_events=list(runtime.dataset.events),
            replay_llm=load_llm_records(Path(dataset_dir)),
            dataset_name=runtime.dataset.manifest.dataset,
            filter_cfg=seat_filter,
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
    store: LedgerStore | None = None,
    promotion_check: Callable[[LedgerStore, Clock], None] | None = None,
    resume_after: float | None = None,
    rules_reload: Callable[[], None] | None = None,
) -> list[dict[str, str]]:
    """Advance the fixture clock along the recording and tick the supervisor at each tick.

    Each recorded tick is one supervisor tick at its own time, so a BUY is judged and
    priced at its own tick and an exit rule sees every later tick in order. A tick the
    clock has already passed (an order's latency moved it on) is skipped, never replayed
    backwards. ``resume_after``, when given, is the last stamp a resumed ledger already
    holds: a tick at or before it is skipped, so a restart does not run completed ticks.
    With ``hold`` the clock then keeps stepping at the tick cadence until the
    supervisor is stopped, so a serve stays up after its recording ends. ``pace_s`` real
    seconds separate steps (zero for a one-shot run), waited on the injected ``pace`` clock
    (a ``WallClock`` in serve, so production keeps real time; never ``asyncio.sleep``).
    ``promotion_check``, when given with ``store``, runs once after each supervisor tick as
    ``promotion_check(store, clock)``. ``rules_reload`` runs right after it, at the same
    tick boundary. Returns each recorded tick's outcomes.
    """
    clock = supervisor.clock
    if not isinstance(clock, FixtureClock):
        raise RuntimeError("a fixture timeline needs the fixture clock")
    if promotion_check is not None and store is None:
        raise ValueError("promotion_check needs the store it checks")
    ticks: list[dict[str, str]] = []
    for at in stamps:
        if at < clock.now() or (resume_after is not None and at <= resume_after):
            continue
        clock.advance_to(at)
        ticks.append(await supervisor.tick_once(heartbeats=heartbeats))
        _tick_boundary(clock, store, promotion_check, rules_reload)
        if pace_s > 0 and pace is not None:
            await pace.sleep(pace_s)
        if supervisor.stopped:
            return ticks
    if not hold:
        return ticks
    while not supervisor.stopped:
        clock.advance_to(clock.now() + TICK_S)
        await supervisor.tick_once(heartbeats=heartbeats)
        _tick_boundary(clock, store, promotion_check, rules_reload)
        if pace_s > 0 and pace is not None:
            await pace.sleep(pace_s)
    return ticks


def _tick_boundary(
    clock: FixtureClock,
    store: LedgerStore | None,
    promotion_check: Callable[[LedgerStore, Clock], None] | None,
    rules_reload: Callable[[], None] | None,
) -> None:
    """Between two ticks: run the promotion check, then the rule reload it may need.

    The reload follows the check, so a promotion applied at this boundary is in force from
    the next tick. Neither runs inside a tick.
    """
    if promotion_check is not None and store is not None:
        promotion_check(store, clock)
    if rules_reload is not None:
        rules_reload()


@dataclass(frozen=True)
class _ServeParts:
    """One serve build: the supervisor, its metrics and store, and the rule reload."""

    supervisor: Supervisor
    metrics: Metrics
    store: LedgerStore
    rules: _ServeRules
    resumed_at: float | None


def _resume_stamp(store: LedgerStore) -> float | None:
    """Epoch of the last timeline row in the ledger, or None when it holds none.

    Row 1 is the checkpoint verdict ``run_replay`` appends. It is stamped at the recording's
    last stamp, so it is not a timeline row. Sequence numbers run 1..count with no gaps, so
    the last timeline row is the one at ``seq == count``.
    """
    count = store.count()
    if count < 2:
        return None
    tail = store.read(since_seq=count, limit=None)
    return parse_ts_utc(str(tail[-1]["ts_utc"]))


@dataclass
class _ServeRules:
    """Sniper candidates, reloaded from the ledger's active set at tick boundaries.

    ``loaded`` is the active-set hash the running candidates were built from. ``reload``
    changes nothing until the ledger names another set. It then judges the recording again
    under that set's filter. Candidate indices follow the recording, so the placed marks stay
    valid. Every candidate at or before the current tick is marked placed: a reload never buys
    a past tick, and a later tick is judged under the new filter.
    """

    store: LedgerStore
    events: Sequence[Mapping[str, Any]]
    trading: _ReplayTrading
    clock: Clock
    loaded: str | None

    def reload(self) -> None:
        active = read_active_set(self.store)
        if active is None or active == self.loaded:
            return
        param_set = load_verified_param_set(self.store, active)
        candidates = evaluate_candidates(self.events, param_set.candidate().filter_settings())
        now = self.clock.now()
        self.trading.candidates = candidates
        self.trading.attempted.update(i for i, c in enumerate(candidates) if c.ts <= now)
        if self.trading.exits is not None:
            self.trading.exits.reload_exits(param_set.candidate().exits_settings())
        self.loaded = active


def _build_serve(
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
    active_set: ParamSet | None = None,
) -> _ServeParts:
    """Build the serve parts over a replayed ledger; see :func:`build_serve_replay`."""
    run_replay(
        dataset_dir,
        filter_cfg,
        seed=seed,
        ledger_path=ledger_path,
        active_set=active_set,
        resume_existing=True,
    )
    runtime = open_replay_runtime(
        dataset_dir,
        filter_cfg,
        seed=seed,
        ledger_path=ledger_path,
        clock=clock,
        exits=exits,
        budget=budget,
        limits=limits,
        active_set=active_set,
    )
    store = runtime.store
    try:
        resumed_at = _resume_stamp(store)
        if (
            resumed_at is not None
            and isinstance(runtime.clock, FixtureClock)
            and resumed_at > runtime.clock.now()
        ):
            runtime.clock.advance_to(resumed_at)
        trading = _replay_trading(runtime)
        degraded = DegradedState()
        seat_filter = filter_cfg
        if active_set is not None:
            seat_filter = active_set.candidate().filter_settings()
        cycles = _replay_cycles(
            clock=runtime.clock,
            rng=make_rng(seed),
            store=store,
            risk=runtime.risk,
            degraded=degraded,
            dataset_events=list(runtime.dataset.events),
            replay_llm=load_llm_records(Path(dataset_dir)),
            dataset_name=runtime.dataset.manifest.dataset,
            filter_cfg=seat_filter,
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
        rules = _ServeRules(
            store=store,
            events=runtime.dataset.events,
            trading=trading,
            clock=runtime.clock,
            loaded=active_set.content_hash if active_set is not None else None,
        )
    except Exception:
        store.close()
        raise
    return _ServeParts(
        supervisor=supervisor,
        metrics=metrics,
        store=store,
        rules=rules,
        resumed_at=resumed_at,
    )


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
    active_set: ParamSet | None = None,
) -> tuple[Supervisor, Metrics, LedgerStore]:
    """Construct the D1 serve supervisor over a replayed ledger.

    Runs ``run_replay`` once, resuming the ledger a previous start wrote so the
    persisted trailing-stop peaks survive a restart (a missing ledger is built fresh).
    It then wires the ten offline seat cycles from ``_replay_cycles`` with
    ``source="replay"`` so the health body carries ``ledger_source=replay`` (never
    live data). A resumed ledger that already holds timeline rows starts the clock at the
    last of them, so the serve continues its timeline. The returned store stays open; the
    caller closes it after the serve loop.
    """
    parts = _build_serve(
        dataset_dir,
        filter_cfg,
        seed=seed,
        clock=clock,
        ledger_path=ledger_path,
        health_path=health_path,
        exits=exits,
        budget=budget,
        limits=limits,
        active_set=active_set,
    )
    return parts.supervisor, parts.metrics, parts.store


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
    active_set: ParamSet | None = None,
    promotion_check: Callable[[LedgerStore, Clock], None] | None = None,
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
    moving at the tick cadence until stop. ``promotion_check`` runs once per tick, with the
    serve's own store and clock. A resumed ledger continues its timeline from its last
    recorded stamp, and a promotion applied in the loop reloads the candidates at the next
    tick boundary.
    Returns 0.
    """
    parts = _build_serve(
        dataset_dir,
        filter_cfg,
        seed=seed,
        ledger_path=ledger_path,
        health_path=health_path,
        exits=exits,
        budget=budget,
        limits=limits,
        active_set=active_set,
    )
    supervisor, metrics, store = parts.supervisor, parts.metrics, parts.store
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
            store=store,
            promotion_check=promotion_check,
            resume_after=parts.resumed_at,
            rules_reload=parts.rules.reload,
        )
        return 0
    finally:
        await _finish_serve(supervisor, server, store, health_path)
