"""Metrics v2: None semantics, annualization flag, inf/NaN rejection."""

from __future__ import annotations

from decimal import Decimal

import pytest

from pumpgrok.backtest.metrics import MetricsContext
from pumpgrok.backtest.metrics_v2 import summarize_v2
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


def _ctx(initial: int, curve: tuple[int, ...], days: Decimal) -> MetricsContext:
    return MetricsContext(
        initial_equity_lamports=initial,
        equity_curve_lamports=curve,
        elapsed_days=days,
    )


def test_formula_cases() -> None:
    fills = [_fill(1, 1_000), _fill(2, 2_000), _fill(3, 1_500)]
    ctx = _ctx(10_000, (10_100, 10_050, 10_300), Decimal("10"))

    report = summarize_v2(fills, ctx)

    assert report.trade_count == 3
    assert report.turnover_lamports == 4_500
    assert report.exposure_lamports == 2_000
    assert report.total_return == Decimal(300) / Decimal(10_000)
    assert report.max_drawdown == Decimal(50) / Decimal(10_100)
    assert report.win_rate == Decimal(2) / Decimal(3)
    assert report.annualization_valid is True
    assert report.sharpe_ratio is not None
    assert report.realized_net_lamports == 300
    assert report.profit_factor == Decimal(350) / Decimal(50)


def test_zero_trades_yield_none() -> None:
    ctx = _ctx(10_000, (), Decimal("30"))
    report = summarize_v2([], ctx)
    assert report.total_return is None
    assert report.max_drawdown is None
    assert report.sharpe_ratio is None
    assert report.win_rate is None
    assert report.profit_factor is None
    assert report.realized_net_lamports is None
    assert report.trade_count == 0
    assert report.exposure_lamports == 0
    assert report.turnover_lamports == 0


def test_zero_initial_equity_total_return_none() -> None:
    fills = [_fill(1, 100)]
    ctx = _ctx(0, (100,), Decimal("30"))
    assert summarize_v2(fills, ctx).total_return is None


def test_under_seven_days_annualization_invalid() -> None:
    fills = [_fill(1, 100), _fill(2, 100)]
    ctx = _ctx(1_000, (1_100, 1_200), Decimal("6.9"))
    report = summarize_v2(fills, ctx)
    assert report.annualization_valid is False
    assert report.sharpe_ratio is None


def test_seven_days_annualization_valid() -> None:
    fills = [_fill(1, 100), _fill(2, 100)]
    ctx = _ctx(1_000, (1_100, 1_200), Decimal("7"))
    assert summarize_v2(fills, ctx).annualization_valid is True


def test_profit_factor_none_without_loss() -> None:
    fills = [_fill(1, 100), _fill(2, 100)]
    ctx = _ctx(1_000, (1_100, 1_200), Decimal("30"))
    assert summarize_v2(fills, ctx).profit_factor is None


def test_zero_dispersion_sharpe_none() -> None:
    fills = [_fill(1, 100), _fill(2, 100)]
    ctx = _ctx(1_000, (1_000, 1_000), Decimal("30"))
    assert summarize_v2(fills, ctx).sharpe_ratio is None


def test_nonfinite_rejected() -> None:
    fills = [_fill(1, 100)]
    ctx = _ctx(1_000, (1_100,), Decimal("NaN"))
    with pytest.raises(ValueError):
        summarize_v2(fills, ctx)
    ctx_inf = _ctx(1_000, (1_100,), Decimal("Infinity"))
    with pytest.raises(ValueError):
        summarize_v2(fills, ctx_inf)


def test_mismatched_curve_rejected() -> None:
    ctx = _ctx(1_000, (1_100,), Decimal("30"))
    with pytest.raises(ValueError, match="length does not match"):
        summarize_v2([_fill(1, 100), _fill(2, 100)], ctx)


def test_determinism() -> None:
    fills = [_fill(1, 1_000), _fill(2, 2_000)]
    ctx = _ctx(10_000, (10_050, 10_300), Decimal("10"))
    assert summarize_v2(fills, ctx) == summarize_v2(fills, ctx)
