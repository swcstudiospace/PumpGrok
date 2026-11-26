<<<<<<< HEAD
"""Metrics v2 over fills (BT-08, BT-09; CONTEXT D-02/D-03).

Every figure describes realized history; the module offers no
forward-looking statements. Money stays integer lamports; Decimal is used
only for ratios. Undefined ratios are None -- never 0 and never inf --
and annualization needs at least seven elapsed days: below that the
ratio is None and ``annualization_valid`` is False.
=======
"""Metrics v2: the decided seven metrics and the annualization flag (BT-08).

The set was decided 2026-11-15 (owner decision 4) and its count confirmed 2026-11-16: total
return, max drawdown, Sharpe and Sortino ratios (annualized, counted separately), hit rate,
profit factor and expectancy. annualization_valid is a flag, not a metric. Closed round trip
counts are denominators and are not reported here.

An undefined value is None, never 0 and never infinity. Money stays integer lamports, except
expectancy_lamports, a Decimal mean of realized lamports. Ratios are Decimal. Annualization uses
the 365-day basis of backtest/metrics.py and is valid only for windows of at least 7 days.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

<<<<<<< HEAD
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
=======
from pumpgrok.backtest.metrics import ANNUALIZATION_DAYS_PER_YEAR, MetricsContext
from pumpgrok.backtest.roundtrip import RoundTrips

__all__ = ["ANNUALIZATION_FLOOR_DAYS", "MetricsV2", "summarize_v2"]

#: The shortest window that may be annualized (BT-08). Shorter windows set annualization_valid
#: to false and leave the Sharpe and Sortino ratios undefined.
ANNUALIZATION_FLOOR_DAYS = Decimal(7)


@dataclass(frozen=True)
class MetricsV2:
    """The Metrics v2 set for one window. A ratio or mean is None when it is undefined."""
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687

    total_return: Decimal | None
    max_drawdown: Decimal | None
    sharpe_ratio: Decimal | None
<<<<<<< HEAD
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
=======
    sortino_ratio: Decimal | None
    hit_rate: Decimal | None
    profit_factor: Decimal | None
    expectancy_lamports: Decimal | None
    annualization_valid: bool


def summarize_v2(book: RoundTrips, context: MetricsContext) -> MetricsV2:
    """Summarize one window from its round trips and its post-fill equity curve.

    The equity curve and elapsed days come from the same window as the round trips. The curve
    has one point per fill step; each step's return is taken against the point before it. Hit
    rate, profit factor and expectancy read the closed round trips only.
    """
    initial = context.initial_equity_lamports
    elapsed = context.elapsed_days
    if initial < 0:
        raise ValueError("initial equity must not be negative")
    if elapsed < 0:
        raise ValueError("elapsed days must not be negative")
    curve = context.equity_curve_lamports
    annualization_valid = elapsed >= ANNUALIZATION_FLOOR_DAYS
    returns = _step_returns(initial, curve)
    factor = _annualization_factor(len(curve), elapsed) if annualization_valid else None
    realized = [trip.realized_lamports for trip in book.closed]
    return MetricsV2(
        total_return=_total_return(initial, curve),
        max_drawdown=_max_drawdown(initial, curve),
        sharpe_ratio=_sharpe(returns, factor) if factor is not None else None,
        sortino_ratio=_sortino(returns, factor) if factor is not None else None,
        hit_rate=_hit_rate(realized),
        profit_factor=_profit_factor(realized),
        expectancy_lamports=_expectancy(realized),
        annualization_valid=annualization_valid,
    )


def _total_return(initial: int, curve: Sequence[int]) -> Decimal | None:
    if initial <= 0:
        return None
    final = curve[-1] if curve else initial
    return Decimal(final - initial) / Decimal(initial)


def _max_drawdown(initial: int, curve: Sequence[int]) -> Decimal | None:
    """Largest peak-to-point decline as a fraction of the running peak.

    The peak starts at initial equity and ratchets up over the curve. A point whose running peak
    is not positive has no defined fraction and is skipped. The result is None only when no peak
    in the window is positive.
    """
    if max((initial, *curve)) <= 0:
        return None
    peak = initial
    worst = Decimal(0)
    for equity in curve:
        peak = max(peak, equity)
        if peak > 0:
            worst = max(worst, Decimal(peak - equity) / Decimal(peak))
    return worst


def _step_returns(initial: int, curve: Sequence[int]) -> list[Decimal]:
    """Simple return of each step. A step against a non-positive prior equity has none."""
    returns: list[Decimal] = []
    previous = initial
    for equity in curve:
        if previous > 0:
            returns.append(Decimal(equity - previous) / Decimal(previous))
        previous = equity
    return returns


def _annualization_factor(steps: int, elapsed: Decimal) -> Decimal:
    """sqrt(365 / step_days) where step_days is the window length over its step count."""
    return (Decimal(ANNUALIZATION_DAYS_PER_YEAR) * steps / elapsed).sqrt()


def _all_equal(values: Sequence[Decimal]) -> bool:
    return all(value == values[0] for value in values)


def _sharpe(returns: Sequence[Decimal], factor: Decimal) -> Decimal | None:
    """Mean return over the sample standard deviation, annualized. None when undefined."""
    count = len(returns)
    if count < 2 or _all_equal(returns):
        return None
    mean = sum(returns, Decimal(0)) / count
    variance = sum(((value - mean) ** 2 for value in returns), Decimal(0)) / (count - 1)
    return mean / variance.sqrt() * factor


def _sortino(returns: Sequence[Decimal], factor: Decimal) -> Decimal | None:
    """Mean return over the downside deviation (all steps in the denominator), annualized."""
    count = len(returns)
    if count < 2 or not any(value < 0 for value in returns):
        return None
    mean = sum(returns, Decimal(0)) / count
    downside_squares = sum((min(value, Decimal(0)) ** 2 for value in returns), Decimal(0))
    return mean / (downside_squares / count).sqrt() * factor


def _hit_rate(realized: Sequence[int]) -> Decimal | None:
    if not realized:
        return None
    winners = sum(1 for value in realized if value > 0)
    return Decimal(winners) / Decimal(len(realized))


def _profit_factor(realized: Sequence[int]) -> Decimal | None:
    if not any(value < 0 for value in realized):
        return None
    gross_profit = sum(value for value in realized if value > 0)
    gross_loss = -sum(value for value in realized if value < 0)
    return Decimal(gross_profit) / Decimal(gross_loss)


def _expectancy(realized: Sequence[int]) -> Decimal | None:
    if not realized:
        return None
    return Decimal(sum(realized)) / Decimal(len(realized))
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
