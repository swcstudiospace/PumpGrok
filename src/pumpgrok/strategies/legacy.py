"""legacy_screening: the existing replay decision path, run through the strategy runtime (STR-03).

The screening decision is not reimplemented. LegacyScreening calls the same functions the
replay uses for every candidate: tick_to_candidate and decide_token from engine.pipeline.
Placement and exit passes call the same replay trading wiring the sniper and the exit seat
use, in the same order: marks, then the buys of each stamp, then the rule sells of each
stamp. run_legacy_replay therefore yields the fills run_once_replay yields on the same
dataset, seed and filter.

The adapter writes no ledger rows of its own: no ticket refs and no strategy state.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from pumpgrok.config.settings import FilterSettings
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.engine.models import Token
from pumpgrok.engine.pipeline import BUY, decide_token, tick_to_candidate
from pumpgrok.logging.json import bind_seat
from pumpgrok.replay.fixtures import event_epoch
from pumpgrok.replay.runner import ReplayTrade
from pumpgrok.strategies.base import Intent, StrategyContext, TickSnapshot
from pumpgrok.strategies.runtime import IntentSink, StrategyRuntime
from pumpgrok.supervisor.scheduler.orders import _run_exit_rules, _replay_trading
from pumpgrok.supervisor.scheduler.replay_runtime import (
    REPLAY_BUY_LAMPORTS,
    REPLAY_SLIPPAGE_BPS,
    REPLAY_TICKET,
    _await_order,
    _replay_trade,
    _ReplayTrading,
    open_replay_runtime,
)
from pumpgrok.upgrade.bounds import KeyBound

__all__ = ["LegacyReplay", "LegacyScreening", "run_legacy_replay", "tick_snapshot"]

#: Correlation of the risk seat's halt check, as the serve timeline's supervisor uses.
RISK_CORRELATION = "desk"


def tick_snapshot(event: Mapping[str, Any]) -> TickSnapshot:
    """The runtime's immutable view of one recorded tick, read through the screening mapping."""
    token = tick_to_candidate(event)
    return TickSnapshot(
        mint=token.mint,
        ts=event_epoch(event),
        launch_ts=token.created_timestamp,
        price_lamports=token.sol_in_curve,
        unique_buyers=token.unique_buyers or 0,
        curve_progress=token.curve_progress,
    )


class LegacyScreening:
    """The legacy screening strategy: the replay's own candidate filter, as a strategy.

    It declares no tunable parameters, so it has no bounds. Built with no arguments it is
    unbound and declares no intents. Bound to a recorded dataset and its filter, each tick
    is judged by decide_token at that tick's time, and every BUY becomes one Intent sized at
    the replay buy amount.
    """

    strategy_id: ClassVar[str] = "legacy_screening"
    BOUNDS: ClassVar[Mapping[str, KeyBound]] = {}
    DEFAULTS: ClassVar[Mapping[str, Any]] = {}

    def __init__(
        self,
        *,
        events: Sequence[Mapping[str, Any]] = (),
        filter_cfg: FilterSettings | None = None,
        ids: IdFactory | None = None,
    ) -> None:
        if filter_cfg is not None and ids is None:
            raise ValueError("a bound LegacyScreening needs an IdFactory for decision ids")
        self._filter = filter_cfg
        self._ids = ids
        self._tokens: dict[tuple[str, float], Token] = {}
        for event in events:
            token = tick_to_candidate(event)
            key = (token.mint, event_epoch(event))
            if key in self._tokens:
                raise ValueError(f"two recorded ticks share mint and time: {key}")
            self._tokens[key] = token

    def on_tick(self, context: StrategyContext) -> tuple[Intent, ...]:
        if self._filter is None or self._ids is None:
            return ()
        token = self._tokens.get((context.tick.mint, context.tick.ts))
        if token is None:
            raise ValueError("tick has no recorded candidate in the bound dataset")
        verdict = decide_token(token, self._filter, context.tick.ts)
        if verdict.decision != BUY:
            return ()
        return (
            Intent(
                strategy_id=self.strategy_id,
                mint=token.mint,
                side="buy",
                size_lamports=REPLAY_BUY_LAMPORTS,
                decision_id=self._ids.ulid(),
                reason=verdict.reason,
                version_id=context.version_id,
            ),
        )


async def _place_buy(trading: _ReplayTrading, intent: Intent) -> None:
    """Place one BUY intent through the sniper's granted exec.place, as the replay does."""
    if trading.refresh_marks is not None:
        await trading.refresh_marks()
    payload = trading.place.spec.input_model.model_validate(
        {
            "ticket_id": REPLAY_TICKET,
            "mint": intent.mint,
            "side": "buy",
            "decision_id": intent.decision_id,
            "size_lamports": intent.size_lamports,
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
            mint=intent.mint,
            outcome=outcome,
            reason=reason,
            decision_id=intent.decision_id,
        )
    )


def _placement_sink(trading: _ReplayTrading) -> IntentSink:
    async def sink(intents: tuple[Intent, ...]) -> None:
        for intent in intents:
            if intent.side != "buy":
                raise ValueError("the legacy placement sink places BUY intents only")
            await _place_buy(trading, intent)

    return sink


@dataclass(frozen=True)
class LegacyReplay:
    """Fills and ledger location of one legacy run through the runtime."""

    trades: tuple[ReplayTrade, ...]
    ledger_path: Path
    seq: int


async def _replay(
    dataset_dir: str | Path,
    filter_cfg: FilterSettings,
    *,
    seed: int,
    ledger_path: str | Path | None,
) -> LegacyReplay:
    runtime = open_replay_runtime(
        dataset_dir, filter_cfg, seed=seed, ledger_path=ledger_path
    )
    try:
        trading = _replay_trading(runtime)
        events = list(runtime.dataset.events)
        screen = LegacyScreening(events=events, filter_cfg=filter_cfg, ids=runtime.ids)
        driver = StrategyRuntime(
            clock=runtime.clock,
            strategies=(screen,),
            sink=_placement_sink(trading),
        )

        async def before_stamp(_stamp: float) -> None:
            if trading.refresh_marks is not None:
                await trading.refresh_marks()
            runtime.risk.evaluate_halts(source="replay", correlation_id=RISK_CORRELATION)

        async def after_stamp(_stamp: float) -> None:
            await _run_exit_rules(trading)

        ticks = sorted((tick_snapshot(event) for event in events), key=lambda t: t.ts)
        await driver.run(ticks, before_stamp=before_stamp, after_stamp=after_stamp)
        if not runtime.store.verify():
            raise RuntimeError("legacy replay ledger failed verification")
        seq = int(runtime.store.read(limit=None)[-1]["seq"])
        trades = tuple(trading.attempts)
    finally:
        runtime.store.close()
    return LegacyReplay(trades=trades, ledger_path=runtime.ledger_path, seq=seq)


def run_legacy_replay(
    dataset_dir: str | Path,
    filter_cfg: FilterSettings,
    *,
    seed: int,
    ledger_path: str | Path | None = None,
) -> LegacyReplay:
    """Run legacy_screening through the strategy runtime over one fixture dataset."""
    return asyncio.run(_replay(dataset_dir, filter_cfg, seed=seed, ledger_path=ledger_path))
