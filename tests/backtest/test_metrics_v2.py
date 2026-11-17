"""Metrics v2: hand-computed values, None for every undefined case, annualization boundary."""

from __future__ import annotations

from dataclasses import fields
from decimal import Decimal

import pytest

from pumpgrok.backtest.metrics import MetricsContext
from pumpgrok.backtest.metrics_v2 import MetricsV2, summarize_v2
from pumpgrok.backtest.roundtrip import UNATTRIBUTED, RoundTrip, RoundTrips

# 273.75 days over three steps gives 365 * 3 / 273.75 = 4, so the annualization factor is 2.
YEAR_FACTOR_DAYS = "273.75"
CURVE = (1100, 1045, 1254)  # step returns: 0.1, -0.05, 0.2


def _book(*realized: int) -> RoundTrips:
    trips = tuple(
        RoundTrip(
            mint="MintAAAAAAAA",
            ticket_id="T",
            strategy=UNATTRIBUTED,
            opened_seq=2 * index + 1,
            closed_seq=2 * index + 2,
            fill_count=2,
            realized_lamports=value,
        )
        for index, value in enumerate(realized)
    )
    return RoundTrips(closed=trips, open_positions=())


def _ctx(initial: int, curve: tuple[int, ...], days: str) -> MetricsContext:
    return MetricsContext(
        initial_equity_lamports=initial,
        equity_curve_lamports=curve,
        elapsed_days=Decimal(days),
    )


def test_output_has_exactly_the_decided_fields() -> None:
    names = {field.name for field in fields(MetricsV2)}
    assert names == {
        "total_return",
        "max_drawdown",
        "sharpe_ratio",
        "sortino_ratio",
        "hit_rate",
        "profit_factor",
        "expectancy_lamports",
        "annualization_valid",
    }


def test_total_return_and_max_drawdown_on_a_known_curve() -> None:
    report = summarize_v2(_book(), _ctx(1000, (1100, 900, 1200), "10"))
    assert report.total_return == Decimal("0.2")
    # Peak 1100 falls to 900: 200 / 1100 = 2 / 11.
    assert report.max_drawdown == Decimal(2) / Decimal(11)


def test_sharpe_and_sortino_match_the_hand_computed_values() -> None:
    # Returns 0.1, -0.05, 0.2. Mean 1/12. Sample variance 19/1200, so sample sd is about
    # 0.125832 and Sharpe is 2 * (1/12) / 0.125832, about 1.32452.
    # Downside deviation is sqrt(0.0025 / 3). Sortino is 2 * (1/12) / sqrt(1/1200) = 10/sqrt(3).
    report = summarize_v2(_book(), _ctx(1000, CURVE, YEAR_FACTOR_DAYS))
    assert report.annualization_valid is True
    assert report.sharpe_ratio is not None
    assert report.sortino_ratio is not None
    assert float(report.sharpe_ratio) == pytest.approx(1.3245, rel=1e-3)
    assert float(report.sortino_ratio) == pytest.approx(10 / 3**0.5, rel=1e-4)


def test_annualization_boundary_at_seven_days() -> None:
    under = summarize_v2(_book(), _ctx(1000, CURVE, "6.99"))
    assert under.annualization_valid is False
    assert under.sharpe_ratio is None
    assert under.sortino_ratio is None
    assert under.total_return is not None

    at_floor = summarize_v2(_book(), _ctx(1000, CURVE, "7.00"))
    assert at_floor.annualization_valid is True
    assert at_floor.sharpe_ratio is not None
    assert at_floor.sortino_ratio is not None


def test_zero_dispersion_and_no_downside_leave_ratios_undefined() -> None:
    # Every step is exactly 0.1: sample standard deviation is zero, and no step loses.
    report = summarize_v2(_book(), _ctx(1000, (1100, 1210, 1331), YEAR_FACTOR_DAYS))
    assert report.sharpe_ratio is None
    assert report.sortino_ratio is None


def test_fewer_than_two_returns_leave_ratios_undefined() -> None:
    report = summarize_v2(_book(), _ctx(1000, (1100,), YEAR_FACTOR_DAYS))
    assert report.sharpe_ratio is None
    assert report.sortino_ratio is None


def test_hit_rate_profit_factor_and_expectancy_on_known_round_trips() -> None:
    report = summarize_v2(_book(100, -50, 200), _ctx(1000, CURVE, YEAR_FACTOR_DAYS))
    assert report.hit_rate == Decimal(2) / Decimal(3)
    assert report.profit_factor == Decimal(6)
    assert report.expectancy_lamports == Decimal(250) / Decimal(3)


def test_no_closed_round_trips_leaves_round_trip_metrics_none_not_zero() -> None:
    report = summarize_v2(_book(), _ctx(1000, (), "10"))
    assert report.hit_rate is None
    assert report.profit_factor is None
    assert report.expectancy_lamports is None


def test_no_losing_round_trip_leaves_profit_factor_none() -> None:
    report = summarize_v2(_book(100, 200), _ctx(1000, CURVE, YEAR_FACTOR_DAYS))
    assert report.profit_factor is None
    assert report.hit_rate == Decimal(1)


def test_zero_start_equity_leaves_return_and_drawdown_none() -> None:
    report = summarize_v2(_book(), _ctx(0, (), "10"))
    assert report.total_return is None
    assert report.max_drawdown is None


def test_empty_window_with_capital_is_defined_as_flat() -> None:
    report = summarize_v2(_book(), _ctx(1000, (), "10"))
    assert report.total_return == Decimal(0)
    assert report.max_drawdown == Decimal(0)
    assert report.sharpe_ratio is None


def test_types_are_decimal_for_ratios_and_bool_for_the_flag() -> None:
    report = summarize_v2(_book(100, -50), _ctx(1000, CURVE, YEAR_FACTOR_DAYS))
    assert isinstance(report.total_return, Decimal)
    assert isinstance(report.max_drawdown, Decimal)
    assert isinstance(report.sharpe_ratio, Decimal)
    assert isinstance(report.sortino_ratio, Decimal)
    assert isinstance(report.hit_rate, Decimal)
    assert isinstance(report.profit_factor, Decimal)
    assert isinstance(report.expectancy_lamports, Decimal)
    assert isinstance(report.annualization_valid, bool)


def test_negative_inputs_raise() -> None:
    with pytest.raises(ValueError):
        summarize_v2(_book(), _ctx(-1, (), "10"))
    with pytest.raises(ValueError):
        summarize_v2(_book(), _ctx(1000, (), "-1"))
