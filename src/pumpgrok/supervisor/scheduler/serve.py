"""Replay entry points: one-shot verdicts and the fixture-timeline serve loop."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.core.ids import Clock
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore
from pumpgrok.replay.clock import FixtureClock, WallClock
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
