"""Regression: a partial exit moves units, basis, mark and realized P&L by its own slice.

Greptile review finding 11 (src/pumpgrok/ledger/reducer.py): a partial sell
reduced units and cost basis but left the full position's mark in place, so
equity counted both the sale proceeds and the old mark, and no realized P&L
was booked for the sold slice until the final close.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.ledger.reducer import LedgerState, initial_state, reduce
from pumpgrok.ledger.views import equity_lamports

MINT = "PartialExit111111111111111111111111111111111"
START_EQUITY = 10_000


def _event(seq: int, type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": seq,
        "ts_utc": f"2026-01-01T00:00:{seq:02d}.000001Z",
        "source": "paper",
        "correlation_id": "01J0000000000000000000001",
        "type": type,
        "payload": payload,
    }


def _fill(side: str, units: int, cash_delta: int, network: int = 0) -> dict[str, Any]:
    return {
        "source": "paper",
        "side": side,
        "mint": MINT,
        "filled_units": units,
        "cash_delta_lamports": cash_delta,
        "venue_fee_lamports": 0,
        "network_cost_lamports": network,
    }


def _open_position(units: int = 100, basis: int = 800, mark: int = 1000) -> list[dict[str, Any]]:
    return [
        _event(1, "FillRecorded", _fill("buy", units, -basis)),
        _event(
            2,
            "PositionOpened",
            {
                "source": "paper",
                "mint": MINT,
                "price_entry": "8",
                "token_units": units,
                "cost_basis_lamports": basis,
                "opened_ts_utc": "2026-01-01T00:00:01Z",
            },
        ),
        _event(
            3,
            "MarkToMarket",
            {
                "source": "paper",
                "prices_json": json.dumps(
                    {MINT: {"mtm_lamports": mark, "spot": "10", "source": "curve"}}
                ),
            },
        ),
    ]


def _sell(seq: int, units: int, proceeds: int, network: int = 0) -> dict[str, Any]:
    return _event(seq, "FillRecorded", _fill("sell", units, proceeds, network))


def _close(seq: int, realized: int) -> dict[str, Any]:
    return _event(
        seq,
        "PositionClosed",
        {"source": "paper", "mint": MINT, "realized_pnl_lamports": realized},
    )


def _fold(events: list[dict[str, Any]]) -> LedgerState:
    state = initial_state(
        source="paper", initial_equity_lamports=START_EQUITY, day_utc="2026-01-01"
    )
    for event in events:
        state = reduce(state, event)
    return state


def test_partial_sell_removes_exactly_the_exited_units_and_basis_share() -> None:
    state = _fold([*_open_position(), _sell(4, 40, 400)])
    pos = state.positions[MINT]
    assert pos.token_units == 60
    assert pos.cost_basis_lamports == 480


def test_partial_sell_scales_the_remaining_mark_to_remaining_units() -> None:
    state = _fold([*_open_position(), _sell(4, 40, 400)])
    assert state.positions[MINT].last_mtm_lamports == 600


def test_partial_sell_does_not_count_sale_proceeds_twice_in_equity() -> None:
    before = _fold(_open_position())
    after = _fold([*_open_position(), _sell(4, 40, 400)])
    assert equity_lamports(before) == 10_200
    assert equity_lamports(after) == 10_200
    assert after.peak_equity_lamports == before.peak_equity_lamports == 10_200


def test_partial_sell_books_realized_pnl_for_the_sold_slice() -> None:
    state = _fold([*_open_position(), _sell(4, 40, 400)])
    # 400 proceeds for 40 units against 320 of the 800 basis.
    assert state.counters.realized_today_lamports == 80


def test_partial_then_final_exit_books_total_pnl_exactly_once() -> None:
    partial = _fold([*_open_position(), _sell(4, 40, 400), _sell(5, 60, 650)])
    # The closing fill's slice is booked by PositionClosed, not by the fill.
    assert partial.counters.realized_today_lamports == 80
    closed = _fold([*_open_position(), _sell(4, 40, 400), _sell(5, 60, 650), _close(6, 170)])
    # 170 = 650 proceeds - 480 remaining basis; total = (400 + 650) - 800.
    assert closed.counters.realized_today_lamports == 250
    assert MINT not in closed.positions


def test_uneven_exits_keep_units_basis_mark_and_realized_exact() -> None:
    events = [
        *_open_position(units=7, basis=1000, mark=1400),
        _sell(4, 3, 600),  # basis 1000 * 3 // 7 = 428 leaves 572
        _sell(5, 2, 400),  # basis 572 * 2 // 4 = 286 leaves 286
    ]
    state = _fold(events)
    pos = state.positions[MINT]
    assert pos.token_units == 2
    assert pos.cost_basis_lamports == 286
    assert pos.last_mtm_lamports == 400
    closed = _fold([*events, _close(6, 104)])  # 390 proceeds - 286 remaining basis
    assert closed.counters.realized_today_lamports == 390  # 1390 proceeds - 1000 basis


def test_partial_sale_with_network_cost_lowers_equity_by_that_cost_only() -> None:
    before = _fold(_open_position())
    after = _fold([*_open_position(), _sell(4, 40, 391, network=9)])
    assert equity_lamports(after) == equity_lamports(before) - 9


@pytest.mark.parametrize(
    ("proceeds", "equity_delta"),
    [(350, -50), (400, 0), (450, 0)],
)
def test_partial_sale_never_raises_equity_and_books_shortfall_as_loss(
    proceeds: int, equity_delta: int
) -> None:
    before = _fold(_open_position())
    after = _fold([*_open_position(), _sell(4, 40, proceeds)])
    assert equity_lamports(after) == equity_lamports(before) + equity_delta
    assert after.peak_equity_lamports == before.peak_equity_lamports
