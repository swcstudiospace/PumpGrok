"""STR-03: the runtime drives strategies under slice isolation."""

from __future__ import annotations

import dataclasses

import pytest

from pumpgrok.strategies.allocation import Allocation, AllocationError
from pumpgrok.strategies.base import Intent, StrategyContext, bounds_for
from pumpgrok.strategies.runtime import StrategyRuntime
from pumpgrok.strategies.tape import Tape, Tick


class _FixedStrategy:
    """Test double: emits one buy per decide until its step budget ends."""

    def __init__(self, strategy_id: str, size_lamports: int) -> None:
        self._id = strategy_id
        self._size = size_lamports
        self.ticks_seen = 0

    @property
    def id(self) -> str:
        return self._id

    @property
    def BOUNDS(self) -> dict[str, tuple[int, int]]:
        return bounds_for(self._id)

    def version_id(self, params: dict[str, object]) -> str:
        return f"{self._id}:test"

    def on_tick(self, tick: Tick) -> None:
        self.ticks_seen += 1

    def decide(self, context: StrategyContext) -> Intent | None:
        if self.ticks_seen <= 0:
            return None
        return Intent(
            strategy_id=self._id,
            side="buy",
            mint="MintA",
            size_lamports=self._size,
            reason="test",
        )


class _QuietStrategy(_FixedStrategy):
    def __init__(self, strategy_id: str) -> None:
        super().__init__(strategy_id, 1)
        self.decide_calls = 0

    def decide(self, context: StrategyContext) -> None:
        self.decide_calls += 1
        return None


def _tape() -> Tape:
    return Tape.from_ticks(
        [Tick(ts=float(i), mint="MintA", price_lamports=1000 + 100 * i) for i in range(3)]
    )


def test_runtime_drives_each_strategy_once_per_tick() -> None:
    allocation = Allocation(10_000, {"momentum_breakout": 5000, "mean_reversion": 5000})
    first = _FixedStrategy("momentum_breakout", 100)
    intents = StrategyRuntime(_tape(), {"momentum_breakout": first}, allocation).run()
    assert first.ticks_seen == 3
    assert len(intents) == 3
    assert all(i.strategy_id == "momentum_breakout" for i in intents)


def test_slice_isolation_stops_over_spend() -> None:
    allocation = Allocation(10_000, {"momentum_breakout": 250, "mean_reversion": 5000})
    first = _FixedStrategy("momentum_breakout", 100)
    runtime = StrategyRuntime(_tape(), {"momentum_breakout": first}, allocation)
    with pytest.raises(AllocationError):
        runtime.run()


def test_slices_stay_isolated_across_strategies() -> None:
    allocation = Allocation(1000, {"momentum_breakout": 500, "mean_reversion": 500})
    first = _FixedStrategy("momentum_breakout", 100)
    second = _FixedStrategy("mean_reversion", 100)
    runtime = StrategyRuntime(
        _tape(), {"momentum_breakout": first, "mean_reversion": second}, allocation
    )
    intents = runtime.run()
    assert len(intents) == 6
    assert allocation.available("momentum_breakout") == 200
    assert allocation.available("mean_reversion") == 200


def test_context_mutation_raises() -> None:
    captured: list[StrategyContext] = []

    class Spy(_FixedStrategy):
        def decide(self, context: StrategyContext) -> None:
            captured.append(context)
            return None

    allocation = Allocation(1000, {"momentum_breakout": 1000})
    StrategyRuntime(_tape(), {"momentum_breakout": Spy("momentum_breakout", 1)}, allocation).run()
    assert captured
    with pytest.raises(dataclasses.FrozenInstanceError):
        captured[0].now = 1.0  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        captured[0].tape = ()  # type: ignore[misc]
