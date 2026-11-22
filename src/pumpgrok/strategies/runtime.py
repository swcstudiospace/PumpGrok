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
"""

from __future__ import annotations

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
