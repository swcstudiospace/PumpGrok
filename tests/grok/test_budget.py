"""Budget is atomic, reserve-aware, restart-safe; fails closed."""

from pathlib import Path

from pumpgrok.grok.budget import LayeredBudget


def test_debit_consumes_all_layers() -> None:
    budget = LayeredBudget(window_cap=100, agent_cap=40, global_cap=200)
    assert budget.try_debit("scout", 1)
    assert budget.window_spent == 1
    assert budget.global_spent == 1
    assert budget.spent_for("scout") == 1


def test_reserve_share_kept_for_reserve_debits() -> None:
    budget = LayeredBudget(window_cap=100, agent_cap=200, global_cap=500)
    for _ in range(75):
        assert budget.try_debit("scout", 1)
    assert not budget.try_debit("scout", 1)
    assert budget.try_debit("scout", 1, use_reserve=True)


def test_restart_keeps_spent(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    first = LayeredBudget(window_cap=100, agent_cap=40, global_cap=200, path=path)
    assert first.try_debit("scout", 3)
    second = LayeredBudget(window_cap=100, agent_cap=40, global_cap=200, path=path)
    assert second.window_spent == 3
    assert second.spent_for("scout") == 3
    assert second.try_debit("scout", 1)
    assert second.window_spent == 4


def test_per_agent_cap_refuses_without_side_effects() -> None:
    budget = LayeredBudget(window_cap=100, agent_cap=2, global_cap=200)
    assert budget.try_debit("scout", 2)
    assert not budget.try_debit("scout", 1)
    assert budget.window_spent == 2
    assert budget.spent_for("scout") == 2
