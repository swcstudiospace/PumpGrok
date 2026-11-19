"""Per-strategy exposure slice on the R34 ``max_token_fraction`` row (RSK-01, D17-4).

The row keeps its budget fraction. For a buy attributed to a strategy the cap is that fraction
of equity less only the cost basis the strategy itself holds in the mint: a position opened by
another strategy's ticket is not charged to this one. The desk-wide row (no strategy id) is
unchanged and stays in the engine step.
"""

from __future__ import annotations

from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.reducer import PositionView


def strategy_held_basis(position: PositionView | None, strategy_tickets: frozenset[str]) -> int:
    """Cost basis this strategy holds in the mint; zero when another strategy opened it."""
    if position is None or position.ticket_id not in strategy_tickets:
        return 0
    return int(position.cost_basis_lamports)


def strategy_cap(budget: RiskBudget, equity: int, strategy_basis: int) -> int:
    """Lamports this strategy may still add in the mint: its slice of equity less its own basis."""
    return int(budget.max_token_fraction * equity) - strategy_basis
