"""Event-driven seat cycles for the trading and safety roles (EVT-10, 14-04 slice A).

Each body runs on the bus event that woke its seat (``TRIGGER_EVENT``). A timer start has no
event; the risk and exit bodies then run their pass on the clock, as the EVENT_TIMERS promise.

Each body calls the role's existing service, so the decision is the same one the replay path
makes. Nothing here reads a price from an event payload: prices and reserves come from the curve
source at the injected clock's time, and orders go through the sniper's granted ``exec.place``,
which runs risk and the paper adapter. The exit path does not import the Grok gateway, so no
model call can hold a protective exit.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pumpgrok.core.ids import CorrelationId, bind_correlation
from pumpgrok.engine.pipeline import SKIP, decide_token, tick_to_candidate
from pumpgrok.events.models import Event, EventKind
from pumpgrok.logging.json import bind_seat
from pumpgrok.supervisor.scheduler.degraded import DegradedState, kill_switch_engaged
from pumpgrok.supervisor.scheduler.orders import _run_exit_rules
from pumpgrok.supervisor.scheduler.replay_runtime import (
    REPLAY_BUY_LAMPORTS,
    REPLAY_SLIPPAGE_BPS,
    REPLAY_TICKET,
    _await_order,
    _replay_trade,
    _ReplayTrading,
)
from pumpgrok.supervisor.scheduler.supervisor import TRIGGER_EVENT
from pumpgrok.supervisor.seat_task import CycleFn, SeatContext

if TYPE_CHECKING:
    from pumpgrok.config.settings import FilterSettings
    from pumpgrok.ledger.store import LedgerStore
    from pumpgrok.replay.sources import FixtureCurveSource
    from pumpgrok.risk.engine import RiskEngine

__all__ = ["build_event_cycles"]

CHIEF = "bot-00-chief"
SCOUT = "bot-01-scout"
RISK = "bot-02-risk"
SNIPER = "bot-04-sniper"
RUG = "bot-05-rug"
EXIT = "bot-06-exit"

#: Events on which the sniper stands down: it places nothing while the desk is halted or vetoed.
_WITHHOLD_KINDS = frozenset({EventKind.kill_switch, EventKind.halt, EventKind.risk_veto})


def _trigger_name(event: Event | None) -> str:
    return "timer" if event is None else event.kind.value


async def _refresh_marks(trading: _ReplayTrading) -> None:
    """Mark every open position from the curve source at this instant (never from a payload)."""
    if trading.refresh_marks is not None:
        await trading.refresh_marks()


async def _chief(ctx: SeatContext, *, store: LedgerStore) -> dict[str, Any]:
    """Chief: review the desk state the event arrived in (read-only)."""
    return {
        "autonomy": ctx.autonomy_level,
        "kill_switch": kill_switch_engaged(store),
        "trigger": _trigger_name(TRIGGER_EVENT.get()),
    }


async def _scout(
    ctx: SeatContext, *, curves: FixtureCurveSource, filter_cfg: FilterSettings
) -> dict[str, Any]:
    """Scout: admit a new token through the engine filter on its curve reading.

    Only ``token_created`` is a candidate. A migration is a graduated curve and is not admitted.
    Buyer counts are not on the event, so the filter sees none and fails closed (SKIP).
    """
    event = TRIGGER_EVENT.get()
    if event is None:
        return {"mint": None, "decision": SKIP, "reason": "no_event", "trigger": "timer"}
    mint = event.entity_id
    trigger = event.kind.value
    if event.kind is not EventKind.token_created:
        return {"mint": mint, "decision": SKIP, "reason": "not_a_new_token", "trigger": trigger}
    snapshot = await curves.curve(mint)
    if snapshot is None:
        return {"mint": mint, "decision": SKIP, "reason": "no_curve", "trigger": trigger}
    name = event.payload.get("name")
    token = tick_to_candidate(
        {
            "mint": mint,
            "name": name if isinstance(name, str) else None,
            "created_ts_utc": event.occurred_at,
            "S": snapshot.s_lamports,
            "complete": snapshot.complete,
        }
    )
    verdict = decide_token(token, filter_cfg, ctx.clock.now())
    return {"mint": mint, "decision": verdict.decision, "reason": verdict.reason, "trigger": trigger}


async def _risk(ctx: SeatContext, *, risk: RiskEngine, trading: _ReplayTrading) -> dict[str, Any]:
    """Risk: refresh marks, then evaluate the daily-loss and drawdown halts."""
    await _refresh_marks(trading)
    verdict = risk.evaluate_halts(source=ctx.source, correlation_id=ctx.correlation_id)
    return {"halt": verdict, "trigger": _trigger_name(TRIGGER_EVENT.get())}


async def _place_buy(trading: _ReplayTrading, mint: str) -> dict[str, Any]:
    """One BUY through the sniper's granted ``exec.place``; risk and the adapter decide."""
    decision_id = trading.ids.ulid()
    payload = trading.place.spec.input_model.model_validate(
        {
            "ticket_id": REPLAY_TICKET,
            "mint": mint,
            "side": "buy",
            "decision_id": decision_id,
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
    trading.attempts.append(
        _replay_trade(
            trading.store,
            side="buy",
            mint=mint,
            outcome=outcome,
            reason=reason,
            decision_id=decision_id,
        )
    )
    return {"status": outcome, "reason": reason}


async def _sniper(ctx: SeatContext, *, trading: _ReplayTrading) -> dict[str, Any]:
    """Sniper: buy on a strategy intent; stand down on a kill switch, halt or risk veto."""
    event = TRIGGER_EVENT.get()
    trigger = _trigger_name(event)
    if event is not None and event.kind in _WITHHOLD_KINDS:
        return {"orders": 0, "withheld": event.kind.value, "trigger": trigger}
    if event is None or event.kind is not EventKind.strategy_intent:
        return {"orders": 0, "reason": "not_an_intent", "trigger": trigger}
    if ctx.observe_only:
        return {"orders": 0, "observe_only": True, "trigger": trigger}
    await _refresh_marks(trading)
    placed = await _place_buy(trading, event.entity_id)
    return {"orders": 1, **placed, "trigger": trigger}


async def _rug(ctx: SeatContext, *, degraded: DegradedState, curves: FixtureCurveSource) -> dict[str, Any]:
    """Rug: BLIND when every RPC endpoint is down; UNREAD when the mint's curve cannot be read."""
    event = TRIGGER_EVENT.get()
    mint = None if event is None else event.entity_id
    if degraded.rpc_blind:
        verdict = "BLIND"
    elif mint is None or await curves.curve(mint) is None:
        verdict = "UNREAD"
    else:
        verdict = "CLEAR"
    return {"verdict": verdict, "mint": mint, "trigger": _trigger_name(event)}


async def _exit(ctx: SeatContext, *, store: LedgerStore, trading: _ReplayTrading) -> dict[str, Any]:
    """Exit: one protective rule pass on the curve reads at this instant. No gateway in this path."""
    opened = len(store.read(types=["PositionOpened"], limit=None))
    trigger = _trigger_name(TRIGGER_EVENT.get())
    if ctx.observe_only:
        return {"open": opened, "rule_sells": 0, "trigger": trigger}
    sold = await _run_exit_rules(trading)
    return {"open": opened, "rule_sells": len(sold), "trigger": trigger}


def build_event_cycles(
    *,
    store: LedgerStore,
    risk: RiskEngine,
    degraded: DegradedState,
    trading: _ReplayTrading,
    curves: FixtureCurveSource,
    filter_cfg: FilterSettings,
) -> Mapping[str, CycleFn]:
    """Event-driven bodies for the six trading and safety seats, keyed by seat id.

    ``trading`` must be the runtime's granted wiring (``_replay_trading``): the sniper and the
    exit seat place only through it. Merge over the replay cycles for the other four seats.
    """
    return {
        CHIEF: functools.partial(_chief, store=store),
        SCOUT: functools.partial(_scout, curves=curves, filter_cfg=filter_cfg),
        RISK: functools.partial(_risk, risk=risk, trading=trading),
        SNIPER: functools.partial(_sniper, trading=trading),
        RUG: functools.partial(_rug, degraded=degraded, curves=curves),
        EXIT: functools.partial(_exit, store=store, trading=trading),
    }

