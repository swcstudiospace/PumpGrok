<<<<<<< HEAD
"""Per-strategy capital slices of the desk budget (STR-03).

An :class:`Allocation` caps each strategy at its slice of the desk budget:
slices sum to at most the budget, every spend checks the slice that
remains, and an over-slice buy is rejected (never clamped, never borrowed
from another strategy). Money is integer lamports; risk enforcement of
slices is Phase 17, so this is allocation and attribution only.
=======
"""Integer capital slices per strategy (STR-03).

A slice is equity_lamports * fraction_bps // 10000, floor-divided. The fractions are basis
points, so no value here is a float. Because each slice is floored and the fractions total at
most 10000 bps, the slices sum to at most the equity. Exposure enforcement at the engine is a
later phase (RSK-01); this module only computes the slices.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

<<<<<<< HEAD
from dataclasses import dataclass, field

__all__ = ["Allocation"]


class AllocationError(ValueError):
    """An allocation cannot admit the request (over-slice or unknown id)."""


@dataclass
class Allocation:
    """Slices of one desk budget with spend enforcement."""

    desk_budget_lamports: int
    slices_lamports: dict[str, int]
    _spent_lamports: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            isinstance(self.desk_budget_lamports, bool)
            or not isinstance(self.desk_budget_lamports, int)
            or self.desk_budget_lamports < 0
        ):
            raise ValueError("desk_budget_lamports must be a non-negative int")
        for strategy_id, amount in self.slices_lamports.items():
            if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
                raise ValueError(f"slice {strategy_id!r} must be a non-negative int")
        if sum(self.slices_lamports.values()) > self.desk_budget_lamports:
            raise AllocationError("slices sum past the desk budget")

    def available(self, strategy_id: str) -> int:
        """Lamports remaining in one strategy slice."""
        if strategy_id not in self.slices_lamports:
            raise AllocationError(f"unknown strategy id: {strategy_id!r}")
        return self.slices_lamports[strategy_id] - self._spent_lamports.get(strategy_id, 0)

    def spend(self, strategy_id: str, amount_lamports: int) -> int:
        """Spend from one slice; an over-slice buy raises, never borrows.

        Returns the remaining lamports in the slice after the spend.
        """
        if isinstance(amount_lamports, bool) or not isinstance(amount_lamports, int):
            raise ValueError("amount_lamports must be integer lamports")
        if amount_lamports < 0:
            raise ValueError("amount_lamports must not be negative")
        remaining = self.available(strategy_id)
        if amount_lamports > remaining:
            raise AllocationError(
                f"over-slice spend: {strategy_id!r} requested {amount_lamports} "
                f"of {remaining} remaining"
            )
        spent = self._spent_lamports.get(strategy_id, 0) + amount_lamports
        self._spent_lamports[strategy_id] = spent
        return self.available(strategy_id)
=======
from collections.abc import Mapping

__all__ = ["BPS_FULL", "AllocationError", "slice_lamports"]

BPS_FULL = 10_000


class AllocationError(ValueError):
    """An allocation input is not an integer, is negative, or over-allocates the equity."""


def _as_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AllocationError(f"{name} must be an int")
    return value


def slice_lamports(equity_lamports: int, fractions_bps: Mapping[str, int]) -> dict[str, int]:
    """Each strategy's integer lamport slice of the equity, from its basis-point fraction."""
    equity = _as_int(equity_lamports, "equity_lamports")
    if equity < 0:
        raise AllocationError("equity_lamports must not be negative")
    total = 0
    for name, bps in fractions_bps.items():
        value = _as_int(bps, f"fraction for {name}")
        if value < 0:
            raise AllocationError(f"fraction for {name} must not be negative")
        total += value
    if total > BPS_FULL:
        raise AllocationError(f"fractions total {total} bps, above the {BPS_FULL} bps ceiling")
    return {name: equity * int(bps) // BPS_FULL for name, bps in fractions_bps.items()}
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
