"""Round trips: grouping pairs, partial folds, flagged open trips, sum equality."""

from __future__ import annotations

from pumpgrok.backtest.roundtrip import (
    RoundTripFill,
    group_round_trips,
    per_strategy_breakdown,
)


def _fill(key: str, side: str, lamports: int, strategy_id: str = "") -> RoundTripFill:
    return RoundTripFill(key=key, side=side, lamports=lamports, strategy_id=strategy_id)


def test_open_close_pair() -> None:
    result = group_round_trips([_fill("M", "buy", 100), _fill("M", "sell", 130)])
    assert result.closed == 1
    assert result.unclosed_count == 0
    assert result.wins == 1
    assert result.losses == 0
    assert result.total_realized_net_lamports == 30
    assert result.trips[0].realized_net_lamports == 30


def test_partial_exits_fold() -> None:
    result = group_round_trips(
        [
            _fill("M", "buy", 100),
            _fill("M", "sell", 50),
            _fill("M", "sell", 70),
        ]
    )
    assert result.closed == 1
    assert result.trips[0].exit_lamports == 120
    assert result.total_realized_net_lamports == 20


def test_unclosed_trip_flagged() -> None:
    result = group_round_trips([_fill("M", "buy", 100)])
    assert result.closed == 0
    assert result.unclosed_count == 1
    assert result.trips[0].unclosed is True
    assert result.total_realized_net_lamports == 0


def test_sum_equality_with_metrics_total() -> None:
    fills = [
        _fill("A", "buy", 100, "legacy_screening"),
        _fill("A", "sell", 130, "legacy_screening"),
        _fill("B", "buy", 200, "mean_reversion"),
        _fill("B", "sell", 180, "mean_reversion"),
    ]
    result = group_round_trips(fills)
    assert result.total_realized_net_lamports == 10
    breakdown = per_strategy_breakdown(result)
    assert sum(breakdown.values()) == result.total_realized_net_lamports
    assert breakdown == {"legacy_screening": 30, "mean_reversion": -20}


def test_losing_round_trip() -> None:
    result = group_round_trips([_fill("M", "buy", 100), _fill("M", "sell", 80)])
    assert result.losses == 1
    assert result.total_realized_net_lamports == -20


def test_keys_are_independent() -> None:
    result = group_round_trips(
        [
            _fill("A", "buy", 100),
            _fill("B", "buy", 50),
            _fill("A", "sell", 110),
        ]
    )
    assert result.closed == 1
    assert result.unclosed_count == 1
    assert result.total_realized_net_lamports == 10
