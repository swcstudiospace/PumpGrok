"""Metrics regression test: hand-built fills with exact integer expectations."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from math import sqrt

import pytest

from pumpgrok.backtest.metrics import (
    ANNUALIZATION_DAYS_PER_YEAR,
    MetricsContext,
    MetricsReport,
    summarize,
)
from pumpgrok.core.adapter import Fill, FillStatus

_ULID_CANON = "01ARZ3NDEKTSV4RRFFQ69G5FAV"


def _ulid(n: int) -> str:
    suffix = f"{n:04d}"
    return _ULID_CANON[: 26 - len(suffix)] + suffix


def _fill(n: int, filled_lamports: int) -> Fill:
    return Fill(
        order_id=_ulid(n),
        decision_id=_ulid(900 + n),
        status=FillStatus.FILLED,
        venue_tx_ref=f"dry_run:{_ulid(100 + n)}",
        filled_lamports=filled_lamports,
        filled_units=1_000_000 + n,
        filled_fraction=Decimal("1"),
        price_avg=Decimal("100"),
        realised_slippage_bps=0,
        venue_fee_lamports=10,
        network_cost_lamports=9_000,
        route="curve",
        ledger_seq=n,
    )


def _ctx(
    initial: int,
    curve: tuple[int, ...],
    days: Decimal,
    count: int,
) -> MetricsContext:
    assert len(curve) == count
    return MetricsContext(
        initial_equity_lamports=initial,
        equity_curve_lamports=curve,
        elapsed_days=days,
    )


def test_summarize_hand_built_window() -> None:
    fills = [_fill(1, 1_000), _fill(2, 2_000), _fill(3, 1_500)]
    ctx = _ctx(10_000, (10_100, 10_050, 10_300), Decimal("3"), 3)

    report = summarize(fills, ctx)

    assert isinstance(report, MetricsReport)
    assert report.trade_count == 3
    assert report.turnover_lamports == 4_500
    assert report.exposure_lamports == 2_000
    assert report.total_return == Decimal(300) / Decimal(10_000)
    assert report.win_rate == Decimal(2) / Decimal(3)
    assert report.max_drawdown == Decimal(50) / Decimal(10_100)

    step_returns = [Fraction(100, 10_000), Fraction(-50, 10_100), Fraction(250, 10_050)]
    mean = sum(step_returns) / 3
    std = sqrt(float(sum((item - mean) ** 2 for item in step_returns) / 3))
    expected_ratio = float(mean) / std * sqrt(365.0)
    assert abs(float(report.sharpe_ratio) - expected_ratio) < 1e-9
    assert report.sharpe_ratio > 0
    assert ANNUALIZATION_DAYS_PER_YEAR == 365


def test_drawdown_uses_running_peak_not_final_equity() -> None:
    fills = [_fill(1, 100), _fill(2, 100), _fill(3, 100)]
    ctx = _ctx(10_000, (9_000, 9_500, 11_000), Decimal("2"), 3)

    report = summarize(fills, ctx)

    assert report.max_drawdown == Decimal("0.1")
    assert report.total_return == Decimal("0.1")


def test_flat_window_yields_zero_sharpe() -> None:
    fills = [_fill(1, 500), _fill(2, 500)]
    ctx = _ctx(10_000, (10_000, 10_000), Decimal("1"), 2)

    report = summarize(fills, ctx)

    assert report.sharpe_ratio == Decimal(0)
    assert report.win_rate == Decimal(0)
    assert report.total_return == Decimal(0)
    assert report.max_drawdown == Decimal(0)


def test_zero_elapsed_days_yields_zero_sharpe() -> None:
    fills = [_fill(1, 1_000), _fill(2, 2_000)]
    ctx = _ctx(10_000, (10_100, 10_300), Decimal("0"), 2)

    report = summarize(fills, ctx)

    assert report.sharpe_ratio == Decimal(0)
    assert report.total_return == Decimal(300) / Decimal(10_000)


def test_empty_fill_list_yields_defined_zeros() -> None:
    ctx = _ctx(5_000, (), Decimal("1"), 0)

    report = summarize([], ctx)

    assert report == MetricsReport(
        total_return=Decimal(0),
        max_drawdown=Decimal(0),
        sharpe_ratio=Decimal(0),
        win_rate=Decimal(0),
        trade_count=0,
        exposure_lamports=0,
        turnover_lamports=0,
    )


def test_curve_length_mismatch_raises() -> None:
    fills = [_fill(1, 100)]
    ctx = _ctx(10_000, (10_100, 10_200), Decimal("1"), 2)

    with pytest.raises(ValueError, match="does not match fill count"):
        summarize(fills, ctx)


def test_negative_inputs_raise() -> None:
    fills = [_fill(1, 100)]
    with pytest.raises(ValueError, match="initial equity"):
        summarize(fills, _ctx(-1, (100,), Decimal("1"), 1))
    with pytest.raises(ValueError, match="elapsed days"):
        summarize(fills, _ctx(10_000, (10_100,), Decimal("-1"), 1))
