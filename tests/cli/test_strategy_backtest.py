"""backtest --strategy: per-strategy run over a dataset, output == runtime result."""

from __future__ import annotations

import pytest

from pumpgrok.backtest.manifest import _resolve_dataset_dir
from pumpgrok.backtest.strategy_run import run_strategy
from pumpgrok.cli import main as cli_main


def test_backtest_strategy_matches_runtime(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli_main(["backtest", "--fixture", "smoke", "--strategy", "legacy_screening"])
    assert code == 0
    out = capsys.readouterr().out

    expected = run_strategy(_resolve_dataset_dir("smoke"), "legacy_screening", seed=0)
    assert "legacy_screening" in out
    assert str(expected.net_lamports) in out


def test_backtest_strategy_unknown_refused(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(ValueError, match="unknown strategy"):
        cli_main(["backtest", "--fixture", "smoke", "--strategy", "nope"])
