"""Per-strategy P&L attribution folded to the desk total (STR-03).

:class:`AttributionFold` proves one bank of strategy P&L (integer
lamports, one entry per strategy id) sums exactly to the reported desk
total. A mismatch raises instead of reconciling silently, so attribution
can never drift from the ledger. Legacy screening folds with its own
realized P&L like any other entry; it writes no attribution refs (that
rule lives in :mod:`pumpgrok.ledger.strategy_state`), which does not stop
its P&L from counting toward the desk total.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["AttributionFold", "fold_attribution"]


@dataclass(frozen=True)
class AttributionFold:
    """Fold result: per-strategy integer P&L and the desk total."""

    per_strategy: dict[str, int] = field(default_factory=dict)
    desk_total_lamports: int = 0

    @property
    def folded_lamports(self) -> int:
        """Sum of the per-strategy entries in integer lamports."""
        return sum(self.per_strategy.values())


def fold_attribution(
    per_strategy: dict[str, int], desk_total_lamports: int
) -> AttributionFold:
    """Fold per-strategy P&L and prove the folder equals the desk total.

    Raises ValueError when the fold and the desk total disagree, or when
    any entry is not integer lamports (bool is rejected as non-money).
    """
    for strategy_id, value in per_strategy.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"strategy {strategy_id!r}: realized P&L must be int lamports")
    fold = AttributionFold(per_strategy=dict(per_strategy), desk_total_lamports=desk_total_lamports)
    if fold.folded_lamports != desk_total_lamports:
        raise ValueError(
            f"attribution fold {fold.folded_lamports} != desk total {desk_total_lamports}"
        )
    return fold
