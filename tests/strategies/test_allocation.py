"""STR-03: allocation enforces per-strategy capital slices."""

from __future__ import annotations

import pytest

from pumpgrok.strategies.allocation import Allocation, AllocationError


def test_spend_capped_at_slice() -> None:
    allocation = Allocation(
        desk_budget_lamports=10_000,
        slices_lamports={"momentum_breakout": 4000, "mean_reversion": 6000},
    )
    assert allocation.available("momentum_breakout") == 4000
    assert allocation.spend("momentum_breakout", 1500) == 2500
    with pytest.raises(AllocationError):
        allocation.spend("momentum_breakout", 2501)


def test_slices_never_exceed_desk_budget() -> None:
    with pytest.raises(AllocationError):
        Allocation(1000, {"momentum_breakout": 600, "mean_reversion": 500})


def test_unknown_strategy_refused() -> None:
    allocation = Allocation(1000, {"momentum_breakout": 1000})
    with pytest.raises(AllocationError):
        allocation.spend("no_such_strategy", 1)
    with pytest.raises(AllocationError):
        allocation.available("no_such_strategy")


def test_slices_are_isolated() -> None:
    allocation = Allocation(2000, {"momentum_breakout": 1000, "mean_reversion": 1000})
    allocation.spend("momentum_breakout", 1000)
    assert allocation.available("mean_reversion") == 1000
    with pytest.raises(AllocationError):
        allocation.spend("momentum_breakout", 1)
