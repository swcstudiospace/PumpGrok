"""Strategy runtime: drives strategies tick by tick and hands their Intents to a sink (STR-03).

The runtime holds no store, no ledger handle and no order tool. It advances an injected
fixture clock to each distinct tick time, calls every strategy's hook once per tick with a
frozen StrategyContext, checks each Intent names its own strategy and version, records the
tick on that strategy's tape, and passes the tick's Intents to the sink. Optional hooks run
before and after each stamp. Ticks arrive in timeline order. A tick the clock has already
passed is skipped, as the serve timeline skips it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from itertools import groupby, pairwise
from typing import Protocol

from pumpgrok.replay.clock import FixtureClock
from pumpgrok.strategies.base import (
    Intent,
    Strategy,
    StrategyContext,
    TapePoint,
    TickSnapshot,
    version_id,
)
from pumpgrok.strategies.tape import DEFAULT_TAPE_CAPACITY, Tape

__all__ = ["IntentSink", "StampHook", "StrategyRuntime", "StrategyRuntimeError"]


class StrategyRuntimeError(ValueError):
    """The strategies or ticks given to a run are malformed."""


class IntentSink(Protocol):
    """Receives the Intents one tick produced. The runtime never acts on them itself."""

    async def __call__(self, intents: tuple[Intent, ...]) -> None: ...


StampHook = Callable[[float], Awaitable[None]]


class StrategyRuntime:
    """Runs strategies over a recorded tick timeline and returns their Intents to a sink."""

    def __init__(
        self,
        *,
        clock: FixtureClock,
        strategies: Sequence[Strategy],
        sink: IntentSink,
        tape_capacity: int = DEFAULT_TAPE_CAPACITY,
    ) -> None:
        ids = [strategy.strategy_id for strategy in strategies]
        if len(set(ids)) != len(ids):
            raise StrategyRuntimeError("strategy ids must be unique within one runtime")
        self._clock = clock
        self._strategies = tuple(strategies)
        self._sink = sink
        self._versions = {
            strategy.strategy_id: version_id(type(strategy), dict(type(strategy).DEFAULTS))
            for strategy in strategies
        }
        # EXEC-EX-42: one shared tape (per-mint series), not one copy per strategy.
        self._tape = Tape(capacity=tape_capacity)

    async def run(
        self,
        ticks: Sequence[TickSnapshot],
        *,
        before_stamp: StampHook | None = None,
        after_stamp: StampHook | None = None,
    ) -> None:
        """Replay the ticks in order, one clock stamp at a time."""
        ordered = list(ticks)
        if any(later.ts < earlier.ts for earlier, later in pairwise(ordered)):
            raise StrategyRuntimeError("ticks must arrive in timeline order")
        for stamp, group in groupby(ordered, key=lambda tick: tick.ts):
            if stamp < self._clock.now():
                continue
            self._clock.advance_to(stamp)
            if before_stamp is not None:
                await before_stamp(stamp)
            for tick in group:
                intents = self._decide(tick)
                if intents:
                    await self._sink(intents)
            if after_stamp is not None:
                await after_stamp(stamp)

    def _decide(self, tick: TickSnapshot) -> tuple[Intent, ...]:
        collected: list[Intent] = []
        for strategy in self._strategies:
            strategy_id = strategy.strategy_id
            version = self._versions[strategy_id]
            context = StrategyContext(
                now=self._clock.now(),
                version_id=version,
                tick=tick,
                tape=self._tape.points(tick.mint),
            )
            for intent in strategy.on_tick(context):
                if intent.strategy_id != strategy_id or intent.version_id != version:
                    raise StrategyRuntimeError(
                        f"intent from {strategy_id} names another strategy or version"
                    )
                collected.append(intent)
        self._tape.record(tick.mint, TapePoint(ts=tick.ts, price_lamports=tick.price_lamports))
        return tuple(collected)
