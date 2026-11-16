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
