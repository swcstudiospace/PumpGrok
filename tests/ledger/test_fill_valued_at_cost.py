"""Regression: an open position is valued at its fill cost until its first mark.

A buy moves cash into the position. While the position has no MarkToMarket
yet, equity, drawdown and daily P&L must not read the whole cost as a loss,
since the live daily-loss halt is built on the same equity.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.reducer import LedgerState, initial_state, reduce
from pumpgrok.ledger.views import daily_pnl_fraction, drawdown_fraction, equity_lamports

MINT_A = "AtCostA1111111111111111111111111111111111111"
MINT_B = "AtCostB1111111111111111111111111111111111111"
MINT_C = "AtCostC1111111111111111111111111111111111111"
START_EQUITY = 10_000_000_000
UNITS = 1_000_000


def _event(seq: int, type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": seq,
        "ts_utc": f"2026-01-01T00:00:{seq:02d}.000001Z",
        "source": "paper",
        "correlation_id": "01J0000000000000000000002",
        "type": type,
        "payload": payload,
    }


def _buy(
    seq: int, mint: str, filled: int, *, network: int = 0, venue_fee: int = 0
) -> list[dict[str, Any]]:
    """FillRecorded plus PositionOpened, shaped as the paper adapter writes a first buy.

    The adapter debits filled plus network cost, and that same debit becomes the
    cost basis; the venue fee is already inside the filled amount.
    """
    cash_debit = filled + network
    return [
        _event(
            seq,
            "FillRecorded",
            {
                "source": "paper",
                "side": "buy",
                "mint": mint,
                "filled_lamports": filled,
                "filled_units": UNITS,
                "venue_fee_lamports": venue_fee,
                "network_cost_lamports": network,
                "cash_delta_lamports": -cash_debit,
            },
        ),
        _event(
            seq + 1,
            "PositionOpened",
            {
                "source": "paper",
                "mint": mint,
                "price_entry": "1",
                "token_units": UNITS,
                "cost_basis_lamports": cash_debit,
                "opened_ts_utc": "2026-01-01T00:00:01Z",
            },
        ),
    ]


def _fold(events: list[dict[str, Any]]) -> LedgerState:
    state = initial_state(
        source="paper", initial_equity_lamports=START_EQUITY, day_utc="2026-01-01"
    )
    for event in events:
        state = reduce(state, event)
    return state


def test_unmarked_buy_leaves_equity_exactly_unchanged() -> None:
    before = _fold([])
    after = _fold(_buy(1, MINT_A, 200_000_000))
    assert after.cash_lamports == START_EQUITY - 200_000_000
    assert equity_lamports(after) == equity_lamports(before)


def test_buy_fee_already_inside_the_cash_debit_does_not_reduce_equity() -> None:
    before = _fold([])
    after = _fold(_buy(1, MINT_A, 200_000_000, network=9_000, venue_fee=4_000_000))
    assert equity_lamports(after) == equity_lamports(before)


def test_unmarked_buy_has_zero_drawdown_and_daily_pnl() -> None:
    state = _fold(_buy(1, MINT_A, 200_000_000))
    assert drawdown_fraction(state) == Decimal("0")
    assert daily_pnl_fraction(state) == Decimal("0")


def test_three_unmarked_buys_at_default_size_show_no_phantom_loss() -> None:
    size = int(RiskBudget().max_trade_fraction * START_EQUITY)
    events: list[dict[str, Any]] = []
    for seq, mint in zip((1, 3, 5), (MINT_A, MINT_B, MINT_C), strict=True):
        events.extend(_buy(seq, mint, size))
        assert equity_lamports(_fold(events)) == START_EQUITY
    state = _fold(events)
    assert state.cash_lamports == START_EQUITY - 3 * size
    assert drawdown_fraction(state) == Decimal("0")
    assert daily_pnl_fraction(state) == Decimal("0")
