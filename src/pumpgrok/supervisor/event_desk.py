"""The event desk composition root (RT-03, PRM-05).

One root builds the full event-mode paper desk: the EventBus, the
SourceSupervisor, the strategy runtime, the Grok gateway, the intent
router, the risk engine (with slice, kill and entry checks) and the
promotion evaluator subscribed to evidence and stage events. Building
with any mode other than paper raises before any socket or adapter
exists. The root holds no state of its own; all state lives in the bus
sidecar and the ledger.
"""

from __future__ import annotations

import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pumpgrok.core.adapter import ExecutionMode
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.events.bus import EventBus
from pumpgrok.events.models import Event
from pumpgrok.events.sources import SourceSupervisor
from pumpgrok.grok import GatewayLedger, GatewayRequest, GrokGateway, LayeredBudget
from pumpgrok.promotion.evaluator import EvidenceView, PromotionEvaluator
from pumpgrok.promotion.stages import StageRow, Transition, append_stage_row, append_transition, read_stage_row
from pumpgrok.supervisor.intent_router import IntentRouter, Place
from pumpgrok.supervisor.live_paper import strategy_factory
from pumpgrok.supervisor.recovery import recover
from pumpgrok.risk.feed_health import FeedHealth
from pumpgrok.strategies.allocation import Allocation
from pumpgrok.strategies.runtime import StrategyRuntime
from pumpgrok.strategies.tape import Tape
from pumpgrok.supervisor.intent_router import IntentRouter, Place
from pumpgrok.supervisor.live_paper import strategy_factory

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore

__all__ = ["EventDesk", "EventDeskError", "build_event_desk"]


class EventDeskError(ValueError):
    """The event desk root refused to build."""


async def _replay_transport(_request: GatewayRequest) -> str:
    """Replay transport: recorded-shaped responses, never a network client."""
    return '{"ok": true}'


@dataclass
class EventDesk:
    """The composed paper desk; state lives in the ledger and bus sidecar."""

    mode: str
 
    store: LedgerStore
    clock: Clock
    bus: EventBus
    sources: SourceSupervisor
    runtime: StrategyRuntime
    gateway: GrokGateway
    router: IntentRouter
    risk: RiskEngine
    evaluator: PromotionEvaluator
    feed_health: FeedHealth
    entry_checks: EntryChecks | None = None
    budget: LayeredBudget | None = None
    restored: Any = None

    def handle_evidence(self, evidence: EvidenceView) -> StageRow:
        """Event-triggered promotion evaluation (no timers, no polling)."""
        row = read_stage_row(self.store, evidence.strategy_id)
        previous = row.stage if row is not None else None
        next_stage = self.evaluator.next_stage(previous, evidence)
        new_row = StageRow(
            strategy_id=evidence.strategy_id,
            stage=next_stage,
            version_id=evidence.version_id,
            param_hash=evidence.param_hash,
            evidence_run_id=evidence.evidence_run_id,
            metrics=evidence.metrics,
        )
        if previous is None or next_stage != previous:
            ts = format_ts_utc(self.clock.now())
            append_stage_row(self.store, new_row, by="gate:promotion", ts_utc=ts)
            append_transition(
                self.store,
                Transition(
                    strategy_id=evidence.strategy_id,
                    previous_stage=previous,
                    next_stage=next_stage,
                    evidence_id=evidence.evidence_run_id,
                    event_id=evidence.event_id,
                ),
                by="gate:promotion",
                ts_utc=ts,
            )
        return new_row

    async def _route_event(self, event: Event) -> None:
        """Bus handler: evidence edges reach the promotion evaluator."""
        if str(event.kind) == "strategy_intent":
            payload = dict(event.payload or {})
            evidence = payload.get("evidence")
            if isinstance(evidence, EvidenceView):
                self.handle_evidence(evidence)
            elif isinstance(evidence, dict):
                data = dict(evidence)
                data.setdefault("strategy_id", str(event.entity_id))
                try:
                    self.handle_evidence(EvidenceView(**data))  # type: ignore[arg-type]
                except TypeError:
                    pass


def build_event_desk(
    *,
    mode: ExecutionMode | str,
    store: LedgerStore,
    clock: Clock,
    place: Place,
    strategy_ids: tuple[str, ...] = ("momentum_breakout",),
    params: dict[str, dict[str, Any]] | None = None,
    desk_budget_lamports: int = 1_000_000_000,
    tape: Tape | None = None,
    thresholds: PromotionThresholds | None = None,
    budget: LayeredBudget | None = None,
    entry_checks: EntryChecks | None = None,
    sidecar_path: Path | str | None = None,
    transport: Callable[[GatewayRequest], Awaitable[str]] | None = None,
) -> EventDesk:
    """Compose the paper desk; refuse unless the mode is paper."""
    if mode != ExecutionMode.PAPER:
        raise EventDeskError(f"event desk needs paper mode, got {mode!r}")
    params = params or {}
    strategies: dict[str, Any] = {}
    for strategy_id in strategy_ids:
        strategies[strategy_id] = strategy_factory(strategy_id)(params.get(strategy_id, {}))
    allocation = Allocation(
        desk_budget_lamports=desk_budget_lamports,
        slices_lamports=dict.fromkeys(strategies, desk_budget_lamports),
    )
    runtime = StrategyRuntime(
        tape=tape if tape is not None else Tape(),
        strategies=strategies,
        allocation=allocation,
        params=params,
    )
    real_budget = budget if budget is not None else LayeredBudget(window_cap=100, agent_cap=40, global_cap=200)
    gateway = GrokGateway(
        clock=clock,
        budget=real_budget,
        transport=transport if transport is not None else _replay_transport,
        ledger=GatewayLedger(),
    )
    feed_health = FeedHealth(clock)
    risk = RiskEngine(
        store=store,
        budget=RiskBudget(paper_equity_sol=Decimal(desk_budget_lamports) / Decimal(1_000_000_000)),
        ids=IdFactory(clock, random.Random(11)),
        clock=clock,
        autonomy="autonomous-paper",
        feed_health=feed_health,
    )
    router = IntentRouter(store=store, place=place, clock=clock)
    evaluator = PromotionEvaluator(thresholds if thresholds is not None else load_thresholds())
    sources = SourceSupervisor(clock, random.Random(7), path=sidecar_path or (Path("var") / "events-sidecar.sqlite"))
    holder: dict[str, Any] = {}

    async def _handler(event: Event) -> None:
        desk = holder.get("desk")
        if desk is not None:
            await desk._route_event(event)

    bus = EventBus(clock=clock, handler=_handler, dlq=lambda _ev: None)
    restored = recover(store, clock)
    desk = EventDesk(
        mode=str(mode),
        store=store,
        clock=clock,
        bus=bus,
        sources=sources,
        runtime=runtime,
        gateway=gateway,
        router=router,
        risk=risk,
        evaluator=evaluator,
        feed_health=feed_health,
        entry_checks=entry_checks,
        budget=real_budget,
        restored=restored,
    )
    holder["desk"] = desk
    return desk
