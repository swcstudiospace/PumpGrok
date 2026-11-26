<<<<<<< HEAD
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
=======
"""Round trips: lifecycle grouping, refund exclusion, open marks and the strategy breakdown."""

from __future__ import annotations

from typing import Any

import pytest

from pumpgrok.backtest.roundtrip import (
    UNATTRIBUTED,
    OpenTrip,
    RoundTrip,
    RoundTrips,
    breakdown,
    round_trips,
)

MINT_A = "MintAAAAAAAA"
MINT_B = "MintBBBBBBBB"
MINT_C = "MintCCCCCCCC"
TS = "2026-11-01T00:00:00Z"


def _row(seq: int, row_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": seq,
        "ts_utc": TS,
        "correlation_id": "",
        "type": row_type,
        "payload": payload,
    }


def _fill(seq: int, mint: str, side: str, units: int, cash_delta: int) -> dict[str, Any]:
    return _row(
        seq,
        "FillRecorded",
        {
            "side": side,
            "mint": mint,
            "filled_units": units,
            "cash_delta_lamports": cash_delta,
            "venue_fee_lamports": 0,
            "network_cost_lamports": 0,
        },
    )


def _opened(seq: int, mint: str, ticket: str, units: int, cost_basis: int) -> dict[str, Any]:
    return _row(
        seq,
        "PositionOpened",
        {
            "mint": mint,
            "ticket_id": ticket,
            "price_entry": "1",
            "token_units": units,
            "cost_basis_lamports": cost_basis,
            "opened_ts_utc": TS,
        },
    )


def _closed(seq: int, mint: str, realized: int) -> dict[str, Any]:
    return _row(
        seq,
        "PositionClosed",
        {
            "mint": mint,
            "realized_pnl_lamports": realized,
            "proceeds_lamports": 0,
            "reason": "manual",
        },
    )


def test_partial_sell_stays_in_the_round_trip_it_reduces() -> None:
    # Opening buy: 100 units for 1050 lamports, of which 40 is the ATA deposit.
    # Partial sell of 40 units for 500. Final sell of 60 units for proceeds 800 plus the
    # 40 deposit refunded at close, so the closing credit is 840.
    # Realized P&L: -1050 + 500 + 840 = 290. Treating the refund as profit would give 330.
    rows = [
        _fill(1, MINT_A, "buy", 100, -1050),
        _opened(2, MINT_A, "T1", 100, 1050),
        _fill(3, MINT_A, "sell", 40, 500),
        _fill(4, MINT_A, "sell", 60, 840),
        _closed(5, MINT_A, 290),
    ]
    book = round_trips(rows, {"T1": "alpha"})
    assert book.open_positions == ()
    assert book.closed == (
        RoundTrip(
            mint=MINT_A,
            ticket_id="T1",
            strategy="alpha",
            opened_seq=1,
            closed_seq=4,
            fill_count=3,
            realized_lamports=290,
        ),
    )


def test_two_mints_form_one_closed_and_one_open_round_trip() -> None:
    rows = [
        _fill(1, MINT_A, "buy", 100, -1000),
        _opened(2, MINT_A, "T1", 100, 1000),
        _fill(3, MINT_B, "buy", 50, -500),
        _opened(4, MINT_B, "T2", 50, 500),
        _fill(5, MINT_A, "sell", 100, 1100),
        _closed(6, MINT_A, 100),
    ]
    book = round_trips(rows)
    assert book.closed == (
        RoundTrip(
            mint=MINT_A,
            ticket_id="T1",
            strategy=UNATTRIBUTED,
            opened_seq=1,
            closed_seq=5,
            fill_count=2,
            realized_lamports=100,
        ),
    )
    assert book.open_positions == (
        OpenTrip(
            mint=MINT_B,
            ticket_id="T2",
            strategy=UNATTRIBUTED,
            opened_seq=3,
            fill_count=1,
            mark_lamports=500,
        ),
    )


def test_open_position_at_window_end_is_not_closed_and_holds_its_deposit_as_an_asset() -> None:
    # The 1050 cost basis includes the 40 ATA deposit. While the position is open the deposit
    # is an asset, so the mark carries it and no realized P&L is booked.
    rows = [
        _fill(1, MINT_A, "buy", 100, -1050),
        _opened(2, MINT_A, "T1", 100, 1050),
    ]
    book = round_trips(rows)
    assert book.closed == ()
    assert book.open_positions == (
        OpenTrip(
            mint=MINT_A,
            ticket_id="T1",
            strategy=UNATTRIBUTED,
            opened_seq=1,
            fill_count=1,
            mark_lamports=1050,
        ),
    )


def test_rebuy_after_full_close_starts_a_new_round_trip() -> None:
    rows = [
        _fill(1, MINT_A, "buy", 10, -100),
        _opened(2, MINT_A, "T1", 10, 100),
        _fill(3, MINT_A, "sell", 10, 150),
        _closed(4, MINT_A, 50),
        _fill(5, MINT_A, "buy", 10, -120),
        _opened(6, MINT_A, "T2", 10, 120),
        _fill(7, MINT_A, "sell", 10, 100),
        _closed(8, MINT_A, -20),
    ]
    book = round_trips(rows)
    assert [(t.opened_seq, t.closed_seq, t.realized_lamports) for t in book.closed] == [
        (1, 3, 50),
        (5, 7, -20),
    ]
    assert book.open_positions == ()


def test_breakdown_sums_strategy_keys_including_unattributed_to_the_total() -> None:
    rows = [
        _fill(1, MINT_A, "buy", 10, -100),
        _opened(2, MINT_A, "T1", 10, 100),
        _fill(3, MINT_A, "sell", 10, 130),
        _closed(4, MINT_A, 30),
        _fill(5, MINT_B, "buy", 10, -200),
        _opened(6, MINT_B, "", 10, 200),
        _fill(7, MINT_B, "sell", 10, 150),
        _closed(8, MINT_B, -50),
        _fill(9, MINT_C, "buy", 10, -100),
        _opened(10, MINT_C, "T9", 10, 100),
        _fill(11, MINT_C, "sell", 10, 110),
        _closed(12, MINT_C, 10),
    ]
    # T1 has a reference. The empty ticket and the unreferenced T9 both fall to unattributed.
    book = round_trips(rows, {"T1": "alpha"})
    assert [trip.strategy for trip in book.closed] == ["alpha", UNATTRIBUTED, UNATTRIBUTED]
    assert breakdown(book, 30 - 50 + 10) == {"alpha": 30, UNATTRIBUTED: -40}
    with pytest.raises(ValueError):
        breakdown(book, 0)


def test_breakdown_of_empty_book_is_empty_and_sums_to_zero() -> None:
    assert breakdown(RoundTrips(closed=(), open_positions=()), 0) == {}


def test_sell_with_no_open_position_is_refused() -> None:
    with pytest.raises(ValueError):
        round_trips([_fill(1, MINT_A, "sell", 10, 100)])


def test_sell_of_more_units_than_held_is_refused() -> None:
    rows = [
        _fill(1, MINT_A, "buy", 10, -100),
        _opened(2, MINT_A, "T1", 10, 100),
        _fill(3, MINT_A, "sell", 11, 110),
    ]
    with pytest.raises(ValueError):
        round_trips(rows)
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
