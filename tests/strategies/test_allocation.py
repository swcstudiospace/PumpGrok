<<<<<<< HEAD
"""STR-03: allocation enforces per-strategy capital slices."""
=======
"""STR-03: capital slices are integer lamports, floor-divided, and never exceed equity.

Slice = equity_lamports * fraction_bps // 10000. No slice is computed from a float. A fraction
total above 10000 bps is refused, and so is any non-int, negative or boolean input.
"""
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687

from __future__ import annotations

import pytest

<<<<<<< HEAD
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
=======
from pumpgrok.strategies.allocation import AllocationError, slice_lamports


def test_slice_is_floor_of_equity_times_bps() -> None:
    equity = 1_000_000_007
    slices = slice_lamports(equity, {"momentum_breakout": 2500, "mean_reversion": 5000})
    assert slices == {
        "momentum_breakout": equity * 2500 // 10_000,
        "mean_reversion": equity * 5000 // 10_000,
    }
    assert slices["momentum_breakout"] == 250_000_001
    assert slices["mean_reversion"] == 500_000_003


def test_slices_sum_to_at_most_equity() -> None:
    for equity in (0, 1, 7, 999, 10_000, 123_456_789, 2**80 + 3):
        slices = slice_lamports(equity, {"a": 3333, "b": 3333, "c": 3334})
        assert sum(slices.values()) <= equity


def test_full_allocation_leaves_at_most_one_lamport_per_slice() -> None:
    equity = 999_999_999_999
    slices = slice_lamports(equity, {"a": 6000, "b": 4000})
    assert sum(slices.values()) <= equity
    assert equity - sum(slices.values()) < len(slices)


def test_fraction_total_above_full_is_refused() -> None:
    with pytest.raises(AllocationError):
        slice_lamports(1_000, {"a": 6000, "b": 4001})


def test_slices_are_integers_never_floats() -> None:
    slices = slice_lamports(10**18 + 1, {"a": 1, "b": 9999})
    for value in slices.values():
        assert type(value) is int


@pytest.mark.parametrize("bad_equity", [1.5, True, -1])
def test_non_integer_or_negative_equity_is_refused(bad_equity: object) -> None:
    with pytest.raises(AllocationError):
        slice_lamports(bad_equity, {"a": 100})  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_bps", [2.5, True, -1])
def test_non_integer_or_negative_fraction_is_refused(bad_bps: object) -> None:
    with pytest.raises(AllocationError):
        slice_lamports(1_000, {"a": bad_bps})  # type: ignore[dict-item]
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
