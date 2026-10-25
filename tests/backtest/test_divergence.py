"""PAP-02: divergence on the D7 defaults alerts and blocks promotion."""

from __future__ import annotations

from decimal import Decimal

from pumpgrok.backtest.divergence import (
    ABSOLUTE_RETURN_GAP_PP,
    SHARPE_GAP,
    breach_line,
    check,
    enforce,
)
from pumpgrok.backtest.metrics import MetricsReport
from pumpgrok.backtest.report import BacktestReport, render, with_divergence


def _metrics(total_return: str, sharpe: str) -> MetricsReport:
    return MetricsReport(
        total_return=Decimal(total_return),
        max_drawdown=Decimal(0),
        sharpe_ratio=Decimal(sharpe),
        win_rate=Decimal("0.5"),
        trade_count=2,
        exposure_lamports=1_000,
        turnover_lamports=2_000,
    )


def _report() -> BacktestReport:
    return BacktestReport(
        run_id="RUNID",
        dataset="smoke-10m",
        dataset_digest="D" * 64,
        seed=20260101,
        filter_settings_hash="0" * 64,
        param_set_hash="1" * 64,
        code_version="CODE",
        holdout_id="smoke-10m-holdout",
        holdout_events=8,
        tuning_events=33,
        trial_count=1,
        max_eligible_trials=20,
        max_allowed_trials=50,
        eligible_for_promotion=True,
        promotion_eligible=True,
        venue_fee_bps=100,
        base_fee_lamports=5_000,
        network_cost_lamports=9_000,
        realized_slippage_bps_total=0,
        realized_fees_lamports_total=0,
    )


def test_defaults_match_project_v3_4() -> None:
    assert ABSOLUTE_RETURN_GAP_PP == 2.0
    assert SHARPE_GAP == 0.5


def test_two_point_return_gap_alerts_and_blocks() -> None:
    verdict = check(_metrics("0.10", "1.0"), _metrics("0.08", "1.0"))
    assert verdict.blocks_promotion is True
    assert abs(verdict.return_gap_pp - 2.0) < 1e-9
    assert verdict.reasons != ()


def test_half_point_sharpe_gap_alerts_and_blocks() -> None:
    verdict = check(_metrics("0.10", "1.5"), _metrics("0.10", "1.0"))
    assert verdict.blocks_promotion is True
    assert verdict.sharpe_gap == 0.5
    assert verdict.reasons != ()


def test_gaps_inside_defaults_pass_without_blocking() -> None:
    verdict = check(_metrics("0.10", "1.2"), _metrics("0.09", "1.0"))
    assert verdict.blocks_promotion is False
    assert verdict.reasons == ()
    assert breach_line(verdict) is None
    assert enforce(verdict) == 0


def test_breach_sets_flag_line_and_exit() -> None:
    verdict = check(_metrics("0.10", "1.0"), _metrics("0.08", "1.0"))
    blocked = with_divergence(_report(), verdict)
    assert blocked.promotion_eligible is False
    assert "DIVERGENCE BREACH" in (breach_line(verdict) or "")
    assert enforce(verdict) == 1
    assert render(blocked).count("promotion_eligible: false") == 1


def test_clean_verdict_leaves_report_unchanged() -> None:
    verdict = check(_metrics("0.10", "1.0"), _metrics("0.10", "1.0"))
    assert with_divergence(_report(), verdict).promotion_eligible is True
