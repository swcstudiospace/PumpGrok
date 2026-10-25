"""Single SOL-to-lamports implementation (INT-04, D-05).

Every conversion path (core helper, CLI size, approval phrase, budget equity)
must agree exactly, with ROUND_HALF_UP at the half-lamport boundary.
Deterministic, no network.
"""

from __future__ import annotations

from decimal import Decimal

from pumpgrok.cli import size_sol_to_lamports
from pumpgrok.core.approvals import _sol_to_lamports
from pumpgrok.core.risk_budget import RiskBudget, budget_equity_lamports
from pumpgrok.core.units import lamports_to_sol, sol_to_lamports, split_lamports


def test_half_lamport_rounds_up() -> None:
    """0.5 lamports rounds to 1 (ROUND_HALF_UP, not banker's rounding)."""
    assert sol_to_lamports(Decimal("0.0000000005")) == 1


def test_just_below_half_lamport_rounds_down() -> None:
    assert sol_to_lamports(Decimal("0.0000000004")) == 0
    assert sol_to_lamports(Decimal("0.0000000014")) == 1


def test_just_above_half_lamport_rounds_up() -> None:
    assert sol_to_lamports(Decimal("0.0000000015")) == 2
    assert sol_to_lamports(Decimal("0.0000000016")) == 2


def test_whole_and_fractional_sol() -> None:
    assert sol_to_lamports(Decimal("1")) == 1_000_000_000
    assert sol_to_lamports(Decimal("0.5")) == 500_000_000
    assert sol_to_lamports(Decimal("10")) == 10_000_000_000


def test_every_entry_point_agrees() -> None:
    """CLI, approval phrase and budget equity share the one implementation."""
    assert size_sol_to_lamports(Decimal("0.0000000015")) == sol_to_lamports(
        Decimal("0.0000000015")
    )
    assert _sol_to_lamports("0.0000000015") == sol_to_lamports(Decimal("0.0000000015"))
    budget = RiskBudget(paper_equity_sol=Decimal("10"))
    assert budget.paper_equity_lamports == sol_to_lamports(Decimal("10"))
    assert budget_equity_lamports(budget) == 10_000_000_000


def test_lamports_to_sol_is_exact() -> None:
    assert lamports_to_sol(Decimal(1_000_000_000)) == Decimal(1)
    assert lamports_to_sol(Decimal(1)) == Decimal("0.000000001")


def test_split_lamports_matches_nine_dp_render() -> None:
    assert split_lamports(1_500_000_000) == (1, 500_000_000)
    assert split_lamports(-2_500_000_000) == (2, 500_000_000)
