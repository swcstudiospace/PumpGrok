"""Bounded backtest metrics with stated annualization (BT-05).

Summarizes one evaluation window from its fills plus the equity curve the
window produced. Money stays integer base units (lamports, token units);
Decimal is used only for ratios. Every reported figure describes realized
history; the module offers no forward-looking statements.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from pumpgrok.core.adapter import Fill

__all__ = [
    "ANNUALIZATION_DAYS_PER_YEAR",
    "MetricsContext",
    "MetricsReport",
    "summarize",
]

#: Days per year used to annualize the Sharpe-style ratio. Crypto markets
#: trade 24/7 with no close days, so a full 365-day year applies.
ANNUALIZATION_DAYS_PER_YEAR = 365


@dataclass(frozen=True)
class MetricsContext:
    """Inputs that situate one fill list inside its evaluation window.

    initial_equity_lamports: integer starting equity in lamports. Must be
    zero or positive; a zero start defines return and drawdown as zero
    because a ratio against a zero base is undefined.

    equity_curve_lamports: post-fill equity in lamports after each fill,
    in the same order as ``fills`` and with exactly the same length. Step
    ``i`` deltas against the previous point (or the initial equity for
    the first step) drive win rate and the Sharpe-style ratio, and the
    running peak over the initial equity plus this curve drives maximum
    drawdown.

    elapsed_days: window length in days as a Decimal. Must be zero or
    positive; zero defines the Sharpe-style ratio as zero because
    annualization needs a positive window. The 365-day annualization
    assumes fills spread evenly over this window.
    """

    initial_equity_lamports: int
    equity_curve_lamports: tuple[int, ...]
    elapsed_days: Decimal


@dataclass(frozen=True)
class MetricsReport:
    """Bounded summary of one realized evaluation window.

    total_return: (final equity minus initial equity) divided by initial
    equity as a Decimal; zero when initial equity is zero. Inputs: final
    point of the context curve and initial equity. Assumption: the curve
    already reflects fees and marks, so no further adjustment applies.

    max_drawdown: largest realized peak-to-point decline as a Decimal
    fraction of the running peak, where the peak starts at initial equity
    and ratchets up over the curve. Inputs: initial equity plus the full
    curve. Assumption: intra-fill moves are invisible, so the drawdown is
    bounded by the sampled post-fill points.

    sharpe_ratio: mean of per-fill simple returns divided by their
    population standard deviation, scaled by the square root of
    ANNUALIZATION_DAYS_PER_YEAR times fill count divided by elapsed days,
    as a Decimal. Zero when fewer than two fills exist, when elapsed days
    is zero, or when dispersion is zero. Inputs: curve step returns and
    elapsed days. Assumptions: fills spread evenly over the window, the
    baseline rate is zero, and Decimal arithmetic runs at the default
    28-digit precision.

    win_rate: fraction of fills whose equity step is positive as a
    Decimal; zero when no fills exist. Inputs: curve step deltas ordered
    by the fill list. Assumption: a fill wins when post-fill equity
    exceeds pre-fill equity.

    trade_count: number of fills summarized. Inputs: the fill list length.

    exposure_lamports: largest single-fill filled_lamports in lamports.
    Inputs: fill notionals. Assumption: the biggest single commitment is
    the reported concentration figure.

    turnover_lamports: sum of filled_lamports over all fills in lamports.
    Inputs: fill notionals.
    """

    total_return: Decimal
    max_drawdown: Decimal
    sharpe_ratio: Decimal
    win_rate: Decimal
    trade_count: int
    exposure_lamports: int
    turnover_lamports: int


def _step_returns(ctx: MetricsContext) -> list[Decimal]:
    """Per-fill simple returns as Decimals in fill order."""
    returns: list[Decimal] = []
    previous = ctx.initial_equity_lamports
    for equity in ctx.equity_curve_lamports:
        if previous > 0:
            returns.append(Decimal(equity - previous) / Decimal(previous))
        else:
            returns.append(Decimal(0))
        previous = equity
    return returns


def _sharpe_ratio(returns: Sequence[Decimal], elapsed_days: Decimal) -> Decimal:
    """Annualized Sharpe-style ratio over per-fill simple returns."""
    count = len(returns)
    if count < 2 or elapsed_days <= 0:
        return Decimal(0)
    mean = sum(returns, Decimal(0)) / Decimal(count)
    variance = sum(((item - mean) ** 2 for item in returns), Decimal(0)) / Decimal(count)
    if variance <= 0:
        return Decimal(0)
    dispersion = variance.sqrt()
    if dispersion == 0:
        return Decimal(0)
    scale = (Decimal(ANNUALIZATION_DAYS_PER_YEAR * count) / elapsed_days).sqrt()
    return mean / dispersion * scale


def summarize(fills: Sequence[Fill], ctx: MetricsContext) -> MetricsReport:
    """Summarize one realized window from its fills and context curve.

    Raises ValueError when the curve length differs from the fill count,
    when initial equity is negative, or when elapsed days is negative.
    An empty fill list yields defined zero metrics without raising.
    """
    if len(ctx.equity_curve_lamports) != len(fills):
        raise ValueError(
            "equity curve length does not match fill count: "
            f"{len(ctx.equity_curve_lamports)} != {len(fills)}"
        )
    if ctx.initial_equity_lamports < 0:
        raise ValueError("initial equity must be zero or positive")
    if ctx.elapsed_days < 0:
        raise ValueError("elapsed days must be zero or positive")
    if not fills:
        return MetricsReport(
            total_return=Decimal(0),
            max_drawdown=Decimal(0),
            sharpe_ratio=Decimal(0),
            win_rate=Decimal(0),
            trade_count=0,
            exposure_lamports=0,
            turnover_lamports=0,
        )

    notionals = [fill.filled_lamports for fill in fills]
    turnover = sum(notionals)
    exposure = max(notionals)

    initial = ctx.initial_equity_lamports
    curve = ctx.equity_curve_lamports
    final = curve[-1]
    total_return = Decimal(final - initial) / Decimal(initial) if initial > 0 else Decimal(0)
    peak = initial
    max_drawdown = Decimal(0)
    for equity in curve:
        peak = max(peak, equity)
        if peak > 0:
            decline = Decimal(peak - equity) / Decimal(peak)
            max_drawdown = max(max_drawdown, decline)

    previous_points = (initial, *curve[:-1])
    deltas = [equity - previous for equity, previous in zip(curve, previous_points, strict=True)]
    winners = sum(1 for delta in deltas if delta > 0)
    win_rate = Decimal(winners) / Decimal(len(fills))

    sharpe_ratio = _sharpe_ratio(_step_returns(ctx), ctx.elapsed_days)

    return MetricsReport(
        total_return=total_return,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe_ratio,
        win_rate=win_rate,
        trade_count=len(fills),
        exposure_lamports=exposure,
        turnover_lamports=turnover,
    )
