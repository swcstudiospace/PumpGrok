"""REC-03 strategy half: backtest --strategy prints Metrics v2; v3 stays pinned."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from pumpgrok.backtest import manifest as backtest_manifest
from pumpgrok.cli import main as cli_main
from pumpgrok.cli.errors import UsageError
from pumpgrok.cli.parsing import build_parser

_CHAR_PATH = Path(__file__).with_name("test_backtest_verb_characterization.py")
_CHAR_SPEC = importlib.util.spec_from_file_location(
    "test_backtest_verb_characterization", _CHAR_PATH
)
assert _CHAR_SPEC is not None and _CHAR_SPEC.loader is not None
_CHAR_MOD = importlib.util.module_from_spec(_CHAR_SPEC)
_CHAR_SPEC.loader.exec_module(_CHAR_MOD)
EXPECTED_REPORT = _CHAR_MOD.EXPECTED_REPORT
FIXED_CODE_VERSION = _CHAR_MOD.FIXED_CODE_VERSION

_METRIC_NAMES = (
    "total_return",
    "max_drawdown",
    "sharpe_ratio",
    "sortino_ratio",
    "hit_rate",
    "profit_factor",
    "expectancy_lamports",
)


def _run(
    cwd: Path,
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    cwd.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(cwd)
    capsys.readouterr()
    code = cli_main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_strategy_flag_belongs_to_backtest_only() -> None:
    parser = build_parser()
    parsed = parser.parse_args(["backtest", "--fixture", "smoke", "--strategy", "legacy_screening"])
    assert parsed.strategy == "legacy_screening"
    assert parser.parse_args(["backtest", "--fixture", "smoke"]).strategy is None
    with pytest.raises(UsageError):
        parser.parse_args(["run", "--strategy", "legacy_screening"])


def test_strategy_backtest_is_deterministic_and_prints_metrics_v2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["backtest", "--strategy", "legacy_screening", "--fixture", "smoke"]
    first_code, first, _first_err = _run(tmp_path / "run-a", argv, monkeypatch, capsys)
    second_code, second, _second_err = _run(tmp_path / "run-b", argv, monkeypatch, capsys)
    assert (first_code, second_code) == (0, 0)
    assert first.encode("ascii") == second.encode("ascii")
    assert first.startswith("# PumpGrok strategy backtest\n")
    assert "# PumpGrok backtest report\n" not in first
    assert "cost_basis: fee model v2\n" in first
    assert "fee_model: v2\n" in first
    for name in _METRIC_NAMES:
        assert f"{name}:" in first
    assert "annualization_valid: false\n" in first
    assert "sharpe_ratio: None\n" in first
    assert "sortino_ratio: None\n" in first
    assert "not-applicable" not in first


def test_unknown_strategy_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(
        tmp_path / "unknown",
        ["backtest", "--strategy", "not_a_strategy", "--fixture", "smoke"],
        monkeypatch,
        capsys,
    )
    assert code != 0
    assert out == ""
    assert "unknown strategy" in err


def test_v3_backtest_without_strategy_matches_stored_characterization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stored = tmp_path / "v3-characterization.md"
    stored.write_text(EXPECTED_REPORT, encoding="ascii")
    monkeypatch.setattr(backtest_manifest, "default_code_version", lambda: FIXED_CODE_VERSION)
    code, out, _err = _run(
        tmp_path / "v3", ["backtest", "--fixture", "smoke-10m"], monkeypatch, capsys
    )
    assert code == 0
    assert out == stored.read_text(encoding="ascii")
