"""Strategy replay parity: legacy_screening on smoke == v1 fills and net."""

from __future__ import annotations

import tempfile
from pathlib import Path

from pumpgrok.backtest.evaluate import CandidateParams, EvalWindow, evaluate_window
from pumpgrok.backtest.strategy_run import run_strategy
from pumpgrok.replay.fixtures import event_epoch, load_dataset


def _v1_net(dataset_dir: Path, tmp_path: Path) -> int:
    source = load_dataset(dataset_dir)
    stamps = [event_epoch(event) for event in source.events]
    window = EvalWindow(
        window_id="full", start_ts=min(stamps), end_ts=max(stamps) + 1.0
    )
    return evaluate_window(
        dataset_dir,
        CandidateParams(),
        seed=0,
        ledger_path=tmp_path / "v1.sqlite",
        window=window,
    )


def test_legacy_parity_on_smoke(tmp_path: Path) -> None:
    from pumpgrok.backtest.manifest import _resolve_dataset_dir

    directory = _resolve_dataset_dir("smoke")
    result = run_strategy(directory, "legacy_screening", seed=0, ledger_path=tmp_path / "r.sqlite")
    assert result.strategy_id == "legacy_screening"
    assert result.dataset == "smoke"
    assert result.net_lamports == _v1_net(directory, tmp_path)


def test_other_strategy_runs_through_runtime(tmp_path: Path) -> None:
    from pumpgrok.backtest.manifest import _resolve_dataset_dir

    directory = _resolve_dataset_dir("smoke")
    result = run_strategy(directory, "mean_reversion", seed=0)
    assert result.strategy_id == "mean_reversion"
    assert result.dataset == "smoke"
    assert isinstance(result.net_lamports, int)


def test_unknown_strategy_refused() -> None:
    import pytest

    with tempfile.TemporaryDirectory():
        pass
    with pytest.raises(ValueError, match="unknown strategy"):
        run_strategy("smoke", "not_a_strategy", seed=0)
