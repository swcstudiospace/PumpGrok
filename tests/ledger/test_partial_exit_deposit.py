"""Regression: a partial exit must not dip equity by the outstanding ATA deposit.

FEE-01 holds the first-buy ATA rent as a refundable deposit. The paper adapter
folds that deposit into the position's MarkToMarket value, so the mark carries
market value plus deposit. A partial sell pro-rates the whole mark, so equity
drops by deposit * sold fraction at the sell instant. The deposit must stay
whole until the position closes.

Amounts (lamports, 100 units bought at 800 of market value, 50 deposit):
buy cash 850 = 800 market + 50 rent; mark 850 = 800 market + 50 deposit.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.ledger.reducer import LedgerState, initial_state, reduce
from pumpgrok.ledger.views import equity_lamports

MINT = "DepositExit11111111111111111111111111111111"
START_EQUITY = 10_000
DEPOSIT = 50

# The sidecar's deposit for the buy's PositionOpened, which is seq 2 in every fixture.
OPENING_DEPOSITS = {2: DEPOSIT}


def _event(seq: int, type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": seq,
        "ts_utc": f"2026-01-01T00:00:{seq:02d}.000001Z",
        "source": "paper",
        "correlation_id": "01J0000000000000000000002",
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


def _mark(seq: int, mtm: int) -> dict[str, Any]:
    return _event(
        seq,
        "MarkToMarket",
        {
            "source": "paper",
            "prices_json": json.dumps(
                {
                    MINT: {
                        "mtm_lamports": mtm,
                        "venue_fee_lamports": 0,
                        "spot": "10",
                        "source": "curve",
                    }
                }
            ),
        },
    )


def _open_with_deposit() -> list[dict[str, Any]]:
    return [
        # The first buy's network cost carries the ATA rent (the deposit).
        _event(1, "FillRecorded", _fill("buy", 100, -850, network=DEPOSIT)),
        _event(
            2,
            "PositionOpened",
            {
                "source": "paper",
                "mint": MINT,
                "price_entry": "8",
                "token_units": 100,
                "cost_basis_lamports": 850,
                "opened_ts_utc": "2026-01-01T00:00:02Z",
            },
        ),
        # The paper adapter's mark: 800 market value plus the outstanding deposit.
        _mark(3, 800 + DEPOSIT),
    ]


def _fold(
    events: list[dict[str, Any]], deposits: Mapping[int, int] | None = OPENING_DEPOSITS
) -> LedgerState:
    state = initial_state(
        source="paper", initial_equity_lamports=START_EQUITY, day_utc="2026-01-01"
    )
    for event in events:
        state = reduce(state, event, deposits)
    return state


def test_partial_sell_leaves_equity_unchanged_at_the_sell_instant() -> None:
    before = _fold(_open_with_deposit())
    assert equity_lamports(before) == START_EQUITY
    # Sell 40 of 100 units at its market value of 320; the deposit stays on the books.
    after = _fold([*_open_with_deposit(), _event(4, "FillRecorded", _fill("sell", 40, 320))])
    assert equity_lamports(after) == START_EQUITY


def test_partial_sell_books_no_realized_loss_from_the_deposit() -> None:
    # The sold slice is 320 of market value against 320 of market cost: no P&L.
    state = _fold([*_open_with_deposit(), _event(4, "FillRecorded", _fill("sell", 40, 320))])
    assert state.counters.realized_today_lamports == 0


def test_deposit_stays_carried_after_a_partial_sell() -> None:
    # After the partial sell, the next mark at the same price still carries the
    # whole deposit on the 60 units held: 480 market plus 50 deposit.
    events = [
        *_open_with_deposit(),
        _event(4, "FillRecorded", _fill("sell", 40, 320)),
        _mark(5, 480 + DEPOSIT),
    ]
    assert equity_lamports(_fold(events)) == START_EQUITY


def test_position_is_released_only_by_the_full_close() -> None:
    partial = _fold([*_open_with_deposit(), _event(4, "FillRecorded", _fill("sell", 40, 320))])
    assert set(partial.positions) == {MINT}
    closed = _fold(
        [
            *_open_with_deposit(),
            _event(4, "FillRecorded", _fill("sell", 40, 320)),
            _event(5, "FillRecorded", _fill("sell", 60, 480)),
            _event(
                6,
                "PositionClosed",
                {"source": "paper", "mint": MINT, "realized_pnl_lamports": 0},
            ),
        ]
    )
    assert closed.positions == {}


def test_full_close_refunds_the_deposit_to_cash() -> None:
    # The close fill's cash credit carries the refunded rent: 800 market value plus 50 deposit.
    closing_fill = _event(4, "FillRecorded", _fill("sell", 100, 850))
    released = _fold([*_open_with_deposit(), closing_fill])
    assert released.positions[MINT].token_units == 0
    assert released.positions[MINT].deposit_lamports == 0
    assert released.cash_lamports == START_EQUITY
    closed = _fold(
        [
            *_open_with_deposit(),
            closing_fill,
            _event(
                5,
                "PositionClosed",
                {"source": "paper", "mint": MINT, "realized_pnl_lamports": 0},
            ),
        ]
    )
    assert closed.positions == {}
    assert equity_lamports(closed) == START_EQUITY
    assert closed.counters.realized_today_lamports == 0


def test_legacy_opening_without_a_sidecar_holds_no_deposit() -> None:
    state = _fold(_open_with_deposit(), deposits=None)
    assert state.positions[MINT].deposit_lamports == 0
