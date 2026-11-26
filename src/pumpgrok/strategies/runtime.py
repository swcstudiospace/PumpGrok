<<<<<<< HEAD
"""Strategy runtime with read-only contexts (STR-03).

:class:`StrategyRuntime` is the only entry point that drives strategies:
for each tape tick it calls ``on_tick`` on every registered strategy,
then ``decide`` once per strategy with a frozen context, and charges each
emitted :class:`~pumpgrok.strategies.base.Intent` against the strategy's
capital slice in the allocation. An over-slice Intent raises
:class:`AllocationError` (fail closed, never borrows across slices).
Hooks see the tape as of the current tick (prefix containment), so a
hook cannot observe a future tick through the context. Contexts are
frozen dataclasses, so mutation raises ``FrozenInstanceError``. The
runtime imports no Grok gateway, no engine agent, no network client,
and no timer; determinism comes from the tape, the allocation, and the
injected data only.
=======
"""Strategy runtime: drives strategies tick by tick and hands their Intents to a sink (STR-03).

The runtime holds no store, no ledger handle and no order tool. It advances an injected
fixture clock to each distinct tick time, calls every strategy's hook once per tick with a
frozen StrategyContext, checks each Intent names its own strategy and version, records the
tick on that strategy's tape, and passes the tick's Intents to the sink. Optional hooks run
before and after each stamp. Ticks arrive in timeline order. A tick the clock has already
passed is skipped, as the serve timeline skips it.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

<<<<<<< HEAD
from dataclasses import dataclass
from typing import Any

from pumpgrok.strategies.allocation import Allocation
from pumpgrok.strategies.base import Intent, StrategyContext
from pumpgrok.strategies.tape import Tape

__all__ = ["StrategyRuntime"]


@dataclass(frozen=True)
class _RuntimeContext(StrategyContext):
    """Frozen context handed to hooks: tape snapshot, params, and now."""


class StrategyRuntime:
    """Drive strategies one tick at a time under slice accounting."""

    def __init__(
        self,
        tape: Tape,
        strategies: dict[str, Any],
        allocation: Allocation,
        params: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        if not strategies:
            raise ValueError("a runtime holds at least one strategy")
        self._tape = tape
        self._strategies = dict(strategies)
        self._allocation = allocation
        self._params = params or {}

    @property
    def tape(self) -> Tape:
        """The immutable tape being driven."""
        return self._tape

    def run(self) -> list[Intent]:
        """Drive every tick; charge slices; return intents in emit order."""
        intents: list[Intent] = []
        for index, tick in enumerate(self._tape.ticks):
            for strategy_id, strategy in self._strategies.items():
                strategy.on_tick(tick)
                intent = strategy.decide(
                    _RuntimeContext(
                        tape=self._tape.ticks[: index + 1],
                        params=dict(self._params.get(strategy_id, {})),
                        now=tick.ts,
                    )
                )
                if intent is None:
                    continue
                if intent.strategy_id != strategy_id:
                    raise ValueError(
                        f"strategy {strategy_id!r} emitted an intent for {intent.strategy_id!r}"
                    )
                self._allocation.spend(intent.strategy_id, intent.size_lamports)
                intents.append(intent)
        return intents
=======
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
        self._tapes = {
            strategy.strategy_id: Tape(capacity=tape_capacity) for strategy in strategies
        }

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
            tape = self._tapes[strategy_id]
            context = StrategyContext(
                now=self._clock.now(),
                version_id=version,
                tick=tick,
                tape=tape.points(tick.mint),
            )
            for intent in strategy.on_tick(context):
                if intent.strategy_id != strategy_id or intent.version_id != version:
                    raise StrategyRuntimeError(
                        f"intent from {strategy_id} names another strategy or version"
                    )
                collected.append(intent)
            tape.record(tick.mint, TapePoint(ts=tick.ts, price_lamports=tick.price_lamports))
        return tuple(collected)
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
