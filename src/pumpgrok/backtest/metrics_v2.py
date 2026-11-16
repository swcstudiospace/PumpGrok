"""Metrics v2: the decided seven metrics and the annualization flag (BT-08).

The set was decided 2026-11-15 (owner decision 4) and its count confirmed 2026-11-16: total
return, max drawdown, Sharpe and Sortino ratios (annualized, counted separately), hit rate,
profit factor and expectancy. annualization_valid is a flag, not a metric. Closed round trip
counts are denominators and are not reported here.

An undefined value is None, never 0 and never infinity. Money stays integer lamports, except
expectancy_lamports, a Decimal mean of realized lamports. Ratios are Decimal. Annualization uses
the 365-day basis of backtest/metrics.py and is valid only for windows of at least 7 days.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from pumpgrok.backtest.metrics import ANNUALIZATION_DAYS_PER_YEAR, MetricsContext
from pumpgrok.backtest.roundtrip import RoundTrips

__all__ = ["ANNUALIZATION_FLOOR_DAYS", "MetricsV2", "summarize_v2"]

#: The shortest window that may be annualized (BT-08). Shorter windows set annualization_valid
#: to false and leave the Sharpe and Sortino ratios undefined.
ANNUALIZATION_FLOOR_DAYS = Decimal(7)


@dataclass(frozen=True)
class MetricsV2:
    """The Metrics v2 set for one window. A ratio or mean is None when it is undefined."""

    total_return: Decimal | None
    max_drawdown: Decimal | None
    sharpe_ratio: Decimal | None
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
