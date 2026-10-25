"""Offline replay seat cycles: the ten seats over a fixture timeline (AUTO-006)."""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any

from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.ids import Clock, IdFactory
from pumpgrok.engine.pipeline import decide_replay
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.logging.json import bind_seat
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.runner import llm_request_for
from pumpgrok.supervisor.scheduler.degraded import DegradedState
from pumpgrok.supervisor.scheduler.orders import _place_candidates, _run_exit_rules
from pumpgrok.supervisor.seat_task import SeatContext

if TYPE_CHECKING:
    from pumpgrok.supervisor.scheduler.replay_runtime import _ReplayTrading

log = logging.getLogger("pumpgrok.supervisor.scheduler")


async def _replay_chief(ctx: SeatContext) -> dict[str, Any]:
    """Chief seat: report the autonomy level (read-only)."""
    return {"autonomy": ctx.autonomy_level}


async def _replay_scout(
    ctx: SeatContext, *, dataset_events: list[dict[str, Any]]
) -> dict[str, Any]:
    """Scout seat: count the fixture candidates (read-only)."""
    return {"candidates": len(dataset_events)}


async def _replay_mark_open(trading: _ReplayTrading | None) -> None:
    """Refresh every open position's mark (no-op without a trading wiring)."""
    if trading is not None and trading.refresh_marks is not None:
        await trading.refresh_marks()


async def _replay_risk(
    ctx: SeatContext, *, risk: Any, trading: _ReplayTrading | None
) -> dict[str, Any]:
    """Risk seat: refresh marks, then evaluate the halts (read-only)."""
    await _replay_mark_open(trading)
    verdict = risk.evaluate_halts(source="replay", correlation_id=ctx.correlation_id)
    return {"halt": verdict}


async def _replay_whale(ctx: SeatContext, *, degraded: DegradedState) -> dict[str, Any]:
    """Whale seat: report RPC blindness (read-only)."""
    return {"blind": degraded.rpc_blind}


async def _replay_sniper(
    ctx: SeatContext,
    *,
    clock: Clock,
    rng: Any,
    risk: Any,
    dataset_events: list[dict[str, Any]],
    trading: _ReplayTrading | None,
) -> dict[str, Any]:
    """Sniper seat: one risk check per dataset, or place each BUY candidate."""
    if ctx.observe_only or not dataset_events:
        return {"orders": 0, "observe_only": ctx.observe_only}
    await _replay_mark_open(trading)
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


async def _replay_rug(ctx: SeatContext, *, degraded: DegradedState) -> dict[str, Any]:
    """Rug seat: report the blindness verdict (read-only)."""
    if degraded.rpc_blind:
        return {"verdict": "BLIND"}
    return {"verdict": "CLEAR"}


async def _replay_exit(
    ctx: SeatContext, *, store: LedgerStore, trading: _ReplayTrading | None
) -> dict[str, Any]:
    """Exit seat: count opens, then run one rule pass with a trading wiring."""
    opened = [e for e in store.read(limit=None) if e.get("type") == "PositionOpened"]
    if trading is None or ctx.observe_only:
        return {"open": len(opened), "rule_sells": 0}
    sold = await _run_exit_rules(trading)
    return {"open": len(opened), "rule_sells": len(sold)}


async def _replay_shill(ctx: SeatContext) -> dict[str, Any]:
    """Shill seat: no leads offline (read-only)."""
    return {"leads": 0}


async def _replay_signal(
    ctx: SeatContext,
    *,
    clock: Clock,
    replay_llm: Any | None,
    dataset_name: str,
    dataset_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Signal seat: score on the recorded latency clock (read-only)."""
    if replay_llm is None:
        return {"scoring": "skipped"}
    # Recorded latency is virtual time: only a FixtureClock advances. Under the
    # wall clock it lands on a scratch timeline, never on host time.
    latency_clock = clock if isinstance(clock, FixtureClock) else FixtureClock(start=clock.now())
    request = llm_request_for(dataset_name, list(dataset_events))
    outcome = replay_llm.complete(request, latency_clock)
    return {"scoring": "llm", "outcome": outcome.outcome}


async def _replay_journal(
    ctx: SeatContext,
    *,
    trading: _ReplayTrading | None,
    dataset_events: list[dict[str, Any]],
    filter_cfg: Any,
) -> dict[str, Any]:
    """Journal seat: refresh marks, then fold the replay decision (read-only)."""
    await _replay_mark_open(trading)
    decision = decide_replay(list(dataset_events), filter_cfg)
    return {"decision": decision.decision, "reason": decision.reason}


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
    return {
        "bot-00-chief": _replay_chief,
        "bot-01-scout": functools.partial(_replay_scout, dataset_events=dataset_events),
        "bot-02-risk": functools.partial(_replay_risk, risk=risk, trading=trading),
        "bot-03-whale": functools.partial(_replay_whale, degraded=degraded),
        "bot-04-sniper": functools.partial(
            _replay_sniper,
            clock=clock,
            rng=rng,
            risk=risk,
            dataset_events=dataset_events,
            trading=trading,
        ),
        "bot-05-rug": functools.partial(_replay_rug, degraded=degraded),
        "bot-06-exit": functools.partial(_replay_exit, store=store, trading=trading),
        "bot-07-shill": _replay_shill,
        "bot-08-signal": functools.partial(
            _replay_signal,
            clock=clock,
            replay_llm=replay_llm,
            dataset_name=dataset_name,
            dataset_events=dataset_events,
        ),
        "bot-09-journal": functools.partial(
            _replay_journal,
            trading=trading,
            dataset_events=dataset_events,
            filter_cfg=filter_cfg,
        ),
    }
