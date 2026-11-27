"""The paper MetricsReport is per strategy (Main, 17-04 review).

Two strategies hold one mint in turn. Attribution follows the open ticket on the mint, so each
strategy's report summarizes only its own fills. A window with no attributable fill is refused,
and no desk-window report reaches the gate.
"""

from __future__ import annotations

import pytest
from promotion_support import (
    NOW,
    OTHER_STRATEGY,
    STRATEGY,
    close_position,
    fill,
    open_position,
)

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.promotion import StageRefused
from pumpgrok.promotion.stages import paper_window

MINT = "MintShared1"


def _hold_mint_in_turn(store: LedgerStore) -> None:
    """Strategy A buys and sells MINT; then strategy B buys and sells the same mint."""
    open_position(store, ticket="SOL-A-001", mint=MINT, strategy=STRATEGY)
    fill(store, n=1, side="buy", mint=MINT, lamports=1000)
    fill(store, n=2, side="sell", mint=MINT, lamports=1010)
    close_position(store, mint=MINT, pnl=10, index=1)
    open_position(store, ticket="SOL-B-001", mint=MINT, strategy=OTHER_STRATEGY, cost=2000)
    fill(store, n=3, side="buy", mint=MINT, lamports=2000)
    fill(store, n=4, side="sell", mint=MINT, lamports=2100)
    close_position(store, mint=MINT, pnl=100, index=2, cost=2000)


def test_second_strategy_report_holds_only_its_own_fills(store: LedgerStore) -> None:
    _hold_mint_in_turn(store)

    first = paper_window(store, STRATEGY, now_ts=NOW)
    second = paper_window(store, OTHER_STRATEGY, now_ts=NOW)

    assert first is not None and second is not None
    assert first[1].trade_count == 2
    assert first[1].turnover_lamports == 2010
    assert second[1].trade_count == 2
    assert second[1].turnover_lamports == 4100


def test_pre_open_buy_fill_is_claimed_by_the_open_it_opens(store: LedgerStore) -> None:
    """The buy fill that precedes its PositionOpened counts for that strategy.

    attribution.py leaves such a fill unattributed. The promotion window must count it, since it
    is the fill that opened the strategy's position.
    """
    fill(store, n=30, side="buy", mint="MintPre1", lamports=1000)
    open_position(store, ticket="SOL-PRE-001", mint="MintPre1", strategy=STRATEGY)
    fill(store, n=31, side="sell", mint="MintPre1", lamports=1010)
    close_position(store, mint="MintPre1", pnl=10, index=30)

    window = paper_window(store, STRATEGY, now_ts=NOW)

    assert window is not None
    assert window[1].trade_count == 2
    assert window[1].turnover_lamports == 2010


def test_window_without_attributable_fill_is_refused(store: LedgerStore) -> None:
    open_position(store, ticket="SOL-20260101-900", mint="MintNoFill")
    close_position(store, mint="MintNoFill", pnl=10, index=900)
    with pytest.raises(StageRefused, match="no attributable paper fill"):
        paper_window(store, STRATEGY, now_ts=NOW)


def test_another_strategys_fills_do_not_satisfy_a_window(store: LedgerStore) -> None:
    open_position(store, ticket="SOL-B-002", mint="MintOther2", strategy=OTHER_STRATEGY)
    fill(store, n=10, side="buy", mint="MintOther2", lamports=1000)
    close_position(store, mint="MintOther2", pnl=5, index=10)
    with pytest.raises(StageRefused, match="no attributable paper fill"):
        paper_window(store, STRATEGY, now_ts=NOW)
