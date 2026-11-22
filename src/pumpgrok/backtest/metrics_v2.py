"""Metrics v2 over fills (BT-08, BT-09; CONTEXT D-02/D-03).

Every figure describes realized history; the module offers no
forward-looking statements. Money stays integer lamports; Decimal is used
only for ratios. Undefined ratios are None -- never 0 and never inf --
and annualization needs at least seven elapsed days: below that the
ratio is None and ``annualization_valid`` is False.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from pumpgrok.core.adapter import Fill

__all__ = [
    "ANNUALIZATION_DAYS_PER_YEAR",
    "ANNUALIZATION_MIN_DAYS",
    "MetricsContext",
    "MetricsV2Report",
    "summarize_v2",
]

from pumpgrok.backtest.metrics import (
    ANNUALIZATION_DAYS_PER_YEAR,
    MetricsContext,
    _sharpe_ratio,
    _step_returns,
)

#: Minimum elapsed window for an annualized ratio to be meaningful.
ANNUALIZATION_MIN_DAYS = Decimal("7")


@dataclass(frozen=True)
class MetricsV2Report:
    """Bounded summary of one realized window with None semantics.

    total_return: (final equity minus initial equity) / initial equity;
    None when initial equity is zero (undefined base). Inputs: final
    curve point and initial equity. Assumption: the curve already
    reflects fees and marks.

    max_drawdown: largest realized peak-to-point decline as a fraction of
    the running peak; None when the peak is zero. Inputs: initial equity
    plus the full curve. Assumption: intra-fill moves are invisible.

    sharpe_ratio: mean per-fill step return over population std-dev,
    scaled by sqrt(365 * fills / elapsed days); None when fewer than two
    fills, zero dispersion, non-positive elapsed days, or elapsed days
    below ANNUALIZATION_MIN_DAYS. Inputs: step returns and elapsed days.
    Assumptions: fills spread evenly, baseline rate zero.

    win_rate: fraction of fills whose equity step is positive; None with
    no fills. Inputs: ordered curve deltas.

    trade_count: number of fills. Always defined.

    exposure_lamports: largest single-fill filled_lamports. Inputs: fill
    notionals. 0 with no fills.

    turnover_lamports: sum of filled_lamports. Inputs: fill notionals.

    profit_factor: gross winning steps over gross losing steps (absolute
    lamports); None with no fills, no losing steps, or no winning steps.
    Inputs: ordered curve deltas.

    annualization_valid: True only when elapsed days reaches
    ANNUALIZATION_MIN_DAYS.

    realized_net_lamports: final equity minus initial equity; None with
    no fills. Inputs: final curve point and initial equity.
    """

    total_return: Decimal | None
    max_drawdown: Decimal | None
    sharpe_ratio: Decimal | None
    win_rate: Decimal | None
    trade_count: int
    exposure_lamports: int
    turnover_lamports: int
    profit_factor: Decimal | None
    annualization_valid: bool
    realized_net_lamports: int | None


def _finite(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("metric is not finite")
    return value


def summarize_v2(fills: Sequence[Fill], ctx: MetricsContext) -> MetricsV2Report:
    """Summarize one realized window; undefined ratios come back None.

    Raises ValueError when the curve length differs from the fill count,
    initial equity is negative, elapsed days is negative, or a computed
    ratio is non-finite.
    """
    if len(ctx.equity_curve_lamports) != len(fills):
        raise ValueError(
            "equity curve length does not match fill count: "
            f"{len(ctx.equity_curve_lamports)} != {len(fills)}"
        )
    if ctx.initial_equity_lamports < 0:
        raise ValueError("initial equity must be zero or positive")
    if not ctx.elapsed_days.is_finite():
        raise ValueError("elapsed days must be finite")
    if ctx.elapsed_days < 0:
        raise ValueError("elapsed days must be zero or positive")

    annualization_valid = ctx.elapsed_days >= ANNUALIZATION_MIN_DAYS

    if not fills:
        return MetricsV2Report(
            total_return=None,
            max_drawdown=None,
            sharpe_ratio=None,
            win_rate=None,
            trade_count=0,
            exposure_lamports=0,
            turnover_lamports=0,
            profit_factor=None,
            annualization_valid=annualization_valid,
            realized_net_lamports=None,
        )

    notionals = [fill.filled_lamports for fill in fills]
    turnover = sum(notionals)
    exposure = max(notionals)

    initial = ctx.initial_equity_lamports
    curve = ctx.equity_curve_lamports
    final = curve[-1]

    total_return = _finite(Decimal(final - initial) / Decimal(initial)) if initial > 0 else None

    peak = initial
    max_drawdown_value = Decimal(0)
    for equity in curve:
        peak = max(peak, equity)
        if peak > 0:
            decline = _finite(Decimal(peak - equity) / Decimal(peak))
            max_drawdown_value = max(max_drawdown_value, decline)
    max_drawdown: Decimal | None = max_drawdown_value if peak > 0 else None

    previous_points = (initial, *curve[:-1])
    deltas = [equity - previous for equity, previous in zip(curve, previous_points, strict=True)]
    winners = sum(1 for delta in deltas if delta > 0)
    win_rate = _finite(Decimal(winners) / Decimal(len(fills)))

    gross_profit = sum(delta for delta in deltas if delta > 0)
    gross_loss = sum(-delta for delta in deltas if delta < 0)
    profit_factor = (
        _finite(Decimal(gross_profit) / Decimal(gross_loss))
        if gross_profit > 0 and gross_loss > 0
        else None
    )

    sharpe_ratio: Decimal | None = None
    returns = _step_returns(ctx)
    if annualization_valid and len(returns) >= 2:
        raw = _sharpe_ratio(returns, ctx.elapsed_days)
        if raw != Decimal(0) and raw.is_finite():
            sharpe_ratio = raw

    return MetricsV2Report(
        total_return=total_return,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe_ratio,
        win_rate=win_rate,
        trade_count=len(fills),
        exposure_lamports=exposure,
        turnover_lamports=turnover,
        profit_factor=profit_factor,
        annualization_valid=annualization_valid,
        realized_net_lamports=final - initial,
    )
