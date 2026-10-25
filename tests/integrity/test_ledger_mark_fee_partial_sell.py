"""INT-07: a partial sell scales the stored venue fee pro-rata with the mark.

Ports feature-lineage fix 76975bb onto this tree's ledger/reducer.py: the
fill handler already shrank the stored mark to the remaining units' share,
but it left the stored venue fee at the full holding's value, so a later
close on that mark booked the whole fee for the smaller position. The stored
fee now shrinks pro-rata too (``venue_share``). Deterministic, no network.

Pre-fix behaviour (parent 76975bb^): the fee field was untouched by the
partial sell, so the assertion below failed with the pre-fix signature
``10 != 6`` (full fee kept instead of the 60-units share).
"""

from __future__ import annotations

import json
from typing import Any

from pumpgrok.ledger.reducer import LedgerState, initial_state, reduce

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


def _fold(events: list[dict[str, Any]]) -> LedgerState:
    state = initial_state(
        source="paper", initial_equity_lamports=START_EQUITY, day_utc="2026-01-01"
    )
    for event in events:
        state = reduce(state, event)
    return state


def _marked_position() -> list[dict[str, Any]]:
    """100 units with a 990 mark carrying a 10 venue fee."""
    return [
        _event(
            1,
            "FillRecorded",
            {
                "source": "paper",
                "side": "buy",
                "mint": MINT,
                "filled_units": 100,
                "cash_delta_lamports": -800,
                "venue_fee_lamports": 0,
                "network_cost_lamports": 0,
            },
        ),
        _event(
            2,
            "PositionOpened",
            {
                "source": "paper",
                "mint": MINT,
                "price_entry": "8",
                "token_units": 100,
                "cost_basis_lamports": 800,
                "opened_ts_utc": "2026-01-01T00:00:01Z",
            },
        ),
        _event(
            3,
            "MarkToMarket",
            {
                "source": "paper",
                "prices_json": json.dumps(
                    {MINT: {"mtm_lamports": 990, "venue_fee_lamports": 10, "spot": "10"}}
                ),
            },
        ),
    ]


def test_partial_sell_scales_the_stored_venue_fee_with_the_mark() -> None:
    """Selling 40 of 100 units leaves 60 units holding 10 * 60 // 100 == 6 fee."""
    state = _fold(
        [
            *_marked_position(),
            _event(
                4,
                "FillRecorded",
                {
                    "source": "paper",
                    "side": "sell",
                    "mint": MINT,
                    "filled_units": 40,
                    "cash_delta_lamports": 400,
                    "venue_fee_lamports": 0,
                    "network_cost_lamports": 0,
                },
            ),
        ]
    )
    pos = state.positions[MINT]
    assert pos.token_units == 60
    # Mark is the pro-rata share capped at mark-less-proceeds:
    # min(990 * 60 // 100, 990 - 400) == min(594, 590) == 590.
    assert pos.last_mtm_lamports == 590
    # The fee of the 60 units still held: 10 * 60 // 100 (pre-fix: 10).
    assert pos.last_mtm_venue_fee_lamports == 6
