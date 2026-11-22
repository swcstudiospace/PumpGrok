"""Per-strategy capital slices of the desk budget (STR-03).

An :class:`Allocation` caps each strategy at its slice of the desk budget:
slices sum to at most the budget, every spend checks the slice that
remains, and an over-slice buy is rejected (never clamped, never borrowed
from another strategy). Money is integer lamports; risk enforcement of
slices is Phase 17, so this is allocation and attribution only.
"""

from __future__ import annotations

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
