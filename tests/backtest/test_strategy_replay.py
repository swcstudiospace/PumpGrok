"""BT-12 / criterion 5: strategy replay matches v1 on smoke, and adds no placement path."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pumpgrok.backtest.strategy_run import run_strategy
from pumpgrok.config.settings import FilterSettings
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.strategies.attribution import desk_net_lamports
from pumpgrok.supervisor.scheduler.serve import run_once_replay

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
STRATEGY_RUN = REPO / "src" / "pumpgrok" / "backtest" / "strategy_run.py"
SEED = 20260101
BASELINES = ("momentum_breakout", "new_launch_sniper", "mean_reversion")
FORBIDDEN = frozenset({"_place_buy", "_placement_sink", "_replay", "run_legacy_replay"})


def _net(path: Path) -> int:
    store = LedgerStore(str(path))
    try:
        return desk_net_lamports(store)
    finally:
        store.close()


def test_legacy_screening_matches_run_once_replay(tmp_path: Path) -> None:
    reference = run_once_replay(
        SMOKE, FilterSettings(), seed=SEED, ledger_path=tmp_path / "v1.sqlite"
    )
    result = run_strategy(
        "legacy_screening",
        {},
        SMOKE,
        seed=SEED,
        ledger_path=tmp_path / "strategy.sqlite",
    )
    assert reference.trades, "the smoke replay must place orders"
    assert {trade.side for trade in reference.trades} == {"buy", "sell"}
    assert result.fills == reference.trades
    assert _net(result.ledger_path) == _net(reference.ledger_path)
    assert result.net_lamports == _net(reference.ledger_path)


@pytest.mark.parametrize("strategy_id", BASELINES)
def test_baseline_replay_is_deterministic(tmp_path: Path, strategy_id: str) -> None:
    params: dict[str, object] = {}
    first = run_strategy(
        strategy_id, params, SMOKE, seed=SEED, ledger_path=tmp_path / f"{strategy_id}-a.sqlite"
    )
    second = run_strategy(
        strategy_id, params, SMOKE, seed=SEED, ledger_path=tmp_path / f"{strategy_id}-b.sqlite"
    )
    assert first.fills == second.fills
    assert first.round_trips == second.round_trips
    assert first.metrics_v2 == second.metrics_v2
    assert first.net_lamports == second.net_lamports


def test_strategy_run_adds_no_placement_path() -> None:
    tree = ast.parse(STRATEGY_RUN.read_text(encoding="utf-8"), filename=str(STRATEGY_RUN))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.name.split(".")[-1])
            if node.asname:
                names.add(node.asname)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr != "place":
                continue
            owner = node.func.value
            owner_name = owner.id if isinstance(owner, ast.Name) else ""
            assert "router" in owner_name, "place call on a non-router object"
    assert names.isdisjoint(FORBIDDEN)
