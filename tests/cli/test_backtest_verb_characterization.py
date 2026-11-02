"""Characterization: the `pumpgrok backtest` verb on the smoke-10m fixture (QLT-05, CONTEXT D-10).

Pins the verb's stdout verbatim on the unsplit cli/backtest.py, before the 11-04 split, and
proves two runs print byte-identical reports. The report prints code_version, which defaults to
the git HEAD of the checkout; the pinned run fixes that one input so the pin survives commits.
Every other line is what the verb computes from smoke-10m. stderr carries JSON log lines with
wall-clock timestamps and is not compared. Each run starts in an empty directory because the
verb writes var/backtest under the working directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.backtest import manifest as backtest_manifest
from pumpgrok.cli import main as cli_main

FIXED_CODE_VERSION = "f" * 40

EXPECTED_REPORT = """# PumpGrok backtest report
## Run
code_version: ffffffffffffffffffffffffffffffffffffffff
dataset: smoke-10m
dataset_digest: 2f192b9f3f134f2d92482f0445c32297d45fc54faa8695853abe5ee264da2df7
filter_settings_hash: ad44f6c325f350a860767441bbe1fd3f11ec276effccb098e2ce9af1c9a4d6eb
param_set_hash: d6c9cd2aa6bebb78a249d6fe42fc519d46ac85bcf4af10f96438b054a2990c93
run_id: b2a845ed734638cce870afcd67f22e564ba116724db83f9a3cbccf7f2dd8f74b
seed: 20260101
note: filter_settings_hash identifies the full evaluated configuration: filter, exits, risk budget and limits
## Data window
data_end_utc: 2026-01-01T00:10:00.000Z
data_start_utc: 2026-01-01T00:00:00.000Z
holdout_events: 9
holdout_id: smoke-10m-holdout
split_ids: smoke-10m-train-0,smoke-10m-train-1,smoke-10m-train-2,smoke-10m-train-3,smoke-10m-train-4,smoke-10m-train-5,smoke-10m-train-6,smoke-10m-train-7,smoke-10m-train-8,smoke-10m-train-9,smoke-10m-train-10,smoke-10m-train-11,smoke-10m-train-12,smoke-10m-train-13,smoke-10m-train-14,smoke-10m-train-15,smoke-10m-train-16,smoke-10m-train-17,smoke-10m-train-18,smoke-10m-train-19,smoke-10m-train-20,smoke-10m-train-21,smoke-10m-train-22,smoke-10m-train-23,smoke-10m-train-24,smoke-10m-train-25,smoke-10m-train-26,smoke-10m-train-27,smoke-10m-train-28,smoke-10m-train-29,smoke-10m-train-30,smoke-10m-train-31,smoke-10m-holdout
tuning_events: 32
window_end_utc: 2026-01-01T00:10:00.000000Z
window_start_utc: 2026-01-01T00:08:00.000Z
## Trials
max_allowed_trials: 50
max_eligible_trials: 20
trial_count: 1
trial_limit_eligible: true
## Metrics
elapsed_days: 0.001388888888888888888888888889
exposure_lamports: 0
max_drawdown: not-applicable
sharpe_annualization_days_per_year: 365
sharpe_ratio: not-applicable
total_return: not-applicable
trade_count: 0
turnover_lamports: 0
win_rate: not-applicable
note: BT-05 window metrics from holdout fills in ledger order; inputs are the holdout fills, the cash-delta equity curve from recorded fills, and the window span in days
note: assumptions are fees already reflected in the curve, marks invisible between fills, fills spread evenly for annualization, and a zero baseline rate
note: sharpe-style ratio annualizes with ANNUALIZATION_DAYS_PER_YEAR; crypto markets trade 24/7 with no close days
## Slippage
realized_slippage_bps_total: 0
note: sum of realised_slippage_bps over holdout fills in ledger order
## Fees
base_fee_lamports: 5000
network_cost_lamports: 9000
realized_fees_lamports_total: 0
venue_fee_bps: 100
note: realized total is venue plus network costs summed over holdout fills, plus fees paid by refused attempts (OrderRejected); each fee counts once; schedule fields quote the desk fee model
## Verdict
promotion_eligible: false
promotion_reason: divergence not compared
## Paper comparison
paper_comparison: not compared

"""  # noqa: E501 - the pinned report lines are verbatim verb output and exceed 100 columns


def _run_backtest(
    cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    cwd.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(cwd)
    capsys.readouterr()
    code = cli_main(["backtest", "--fixture", "smoke-10m"])
    return code, capsys.readouterr().out


def test_backtest_smoke_10m_report_is_pinned_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(backtest_manifest, "default_code_version", lambda: FIXED_CODE_VERSION)
    code, out = _run_backtest(tmp_path / "pinned", monkeypatch, capsys)
    assert code == 0
    assert out == EXPECTED_REPORT


def test_two_runs_print_byte_identical_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first_code, first = _run_backtest(tmp_path / "run-a", monkeypatch, capsys)
    second_code, second = _run_backtest(tmp_path / "run-b", monkeypatch, capsys)
    assert (first_code, second_code) == (0, 0)
    assert first.encode("utf-8") == second.encode("utf-8")
    assert first.startswith("# PumpGrok backtest report\n## Run\n")
