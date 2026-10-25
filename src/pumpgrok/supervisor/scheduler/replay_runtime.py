"""Offline replay sandbox: ledger, virtual clock, risk, paper adapter, registry."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pumpgrok.backtest.results import FillDetail
from pumpgrok.config.settings import ExitsSettings
from pumpgrok.core.bot import BotManifest
from pumpgrok.core.ids import Clock, IdFactory
from pumpgrok.core.manifests import load_bot_manifests
from pumpgrok.core.registry import ToolRegistry
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.core.tool import Tool
from pumpgrok.engine.pipeline import CandidateVerdict, evaluate_candidates
from pumpgrok.execution.paper_adapter import PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import FixtureDataset, event_epoch, load_dataset
from pumpgrok.replay.rng import make_rng
from pumpgrok.replay.runner import REPLAY_ROOT, ReplayTrade
from pumpgrok.replay.sources import FixtureCurveSource
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.supervisor.exit_rules import ExitRules
from pumpgrok.tools import build_registry
from pumpgrok.tools.exec.place import build_place_tool
from pumpgrok.tools.risk.kill_switch import build_kill_switch_tool


log = logging.getLogger("pumpgrok.supervisor.scheduler")

REPLAY_TICKET = "SOL-20260101-001"
REPLAY_BUY_LAMPORTS = 10_000_000
REPLAY_SLIPPAGE_BPS = 100
DEFAULT_ROSTER_DIR = Path(__file__).resolve().parents[4] / "contracts" / "tool-rosters"
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


def dataset_events_start(dataset: Any) -> float:
    """First fixture stamp for the replay clock."""
    stamps = [event_epoch(event) for event in dataset.events]
    return min(stamps) if stamps else 0.0


def dataset_stamps(dataset: Any) -> list[float]:
    """Sorted, distinct epoch stamps of the recording: the replay timeline, in order."""
    return sorted({event_epoch(event) for event in dataset.events})


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
    store: LedgerStore | None = None


def _fill_payload_for(
    store: LedgerStore | None, *, decision_id: str = "", mint: str = "", side: str = ""
) -> Mapping[str, Any] | None:
    """Latest FillRecorded payload for one attempt, or None when it never filled.

    A placed order names its decision id; a graduated force-close carries none,
    so it matches the latest sell row for its mint instead. Event types are
    unchanged; the caller reads the added integer fields off the same rows.
    """
    if store is None:
        return None
    match: Mapping[str, Any] | None = None
    for row in store.read(limit=None):
        if row.get("type") != "FillRecorded":
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        if decision_id:
            if str(payload.get("decision_id", "")) != decision_id:
                continue
        elif str(payload.get("mint", "")) != mint or str(payload.get("side", "")) != side:
            continue
        match = payload
    return match


def _replay_trade(
    store: LedgerStore | None,
    *,
    side: str,
    mint: str,
    outcome: str,
    reason: str,
    rule: str = "",
    decision_id: str = "",
) -> ReplayTrade:
    """One replay attempt with per-fill detail from its FillRecorded row (BT-02).

    The place tool reports only status and reason, so the numbers come from the
    ledger row the same call wrote. An attempt with no fill row (rejected,
    unknown) keeps zeroed money fields and its outcome.
    """
    payload = _fill_payload_for(store, decision_id=decision_id, mint=mint, side=side)
    if payload is None:
        return ReplayTrade(side=side, mint=mint, outcome=outcome, reason=reason, rule=rule)
    detail = FillDetail.from_ledger_payload(payload)
    return ReplayTrade(
        side=side,
        mint=mint,
        outcome=outcome,
        reason=reason,
        rule=rule,
        price_avg=detail.price_avg,
        venue_fee_lamports=detail.venue_fee_lamports,
        network_cost_lamports=detail.network_cost_lamports,
        latency_s=detail.latency_s,
        filled_fraction=detail.filled_fraction,
    )


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
