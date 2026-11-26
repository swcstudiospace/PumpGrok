<<<<<<< HEAD
"""Metrics v2: None semantics, annualization flag, inf/NaN rejection."""

from __future__ import annotations

=======
"""Metrics v2: hand-computed values, None for every undefined case, annualization boundary."""

from __future__ import annotations

from dataclasses import fields
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
from decimal import Decimal

import pytest

from pumpgrok.backtest.metrics import MetricsContext
<<<<<<< HEAD
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
=======
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
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
