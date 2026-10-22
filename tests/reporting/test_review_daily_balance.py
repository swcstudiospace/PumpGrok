"""Daily balances come from the ledger's starting equity, folded to the day boundary.

Regression for the review finding that DailyReport started cash at zero and
folded the whole ledger, so a funded account could show negative equity and a
re-rendered past day changed after later trades.
"""

from __future__ import annotations

import json
from pathlib import Path

from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.reporting.daily import DailyReport
from pumpgrok.reporting.render import render_daily

INITIAL = 1_000_000_000
DAY1 = "2026-10-20"
DAY2 = "2026-10-21"
MINT = "So11111111111111111111111111111111111111112"
CID = "01J0000000000000000000000"
BUY_LAMPORTS = 200_000_000
BUY_FEES = 2_009_000
BUY_CASH = -200_009_000
COST_BASIS = 200_009_000
SELL_CASH = 205_000_000
REALIZED = SELL_CASH - COST_BASIS
MARK_LAMPORTS = 250_000_000


def _append(store: LedgerStore, type: str, payload: dict, ts: str) -> None:
    store.append(
        ts_utc=ts,
        source="paper",
        correlation_id=CID,
        idempotency_key=f"{type}-{ts}",
        type=type,
        payload=payload,
    )


def _fill(side: str, lamports: int, cash: int, venue_fee: int, network: int) -> dict:
    return {
        "source": "paper",
        "order_id": f"ord-{side}",
        "decision_id": f"dec-{side}",
        "side": side,
        "mint": MINT,
        "filled_lamports": lamports,
        "filled_units": 1000,
        "filled_fraction": "1",
        "price_avg": "0.00005",
        "venue_fee_lamports": venue_fee,
        "network_cost_lamports": network,
        "cash_delta_lamports": cash,
    }


def _day1_events(store: LedgerStore) -> None:
    _append(
        store,
        "FillRecorded",
        _fill("buy", BUY_LAMPORTS, BUY_CASH, 2_000_000, 9_000),
        DAY1 + "T10:00:00Z",
    )
    _append(
        store,
        "PositionOpened",
        {
            "source": "paper",
            "mint": MINT,
            "price_entry": "0.00005",
            "token_units": 1000,
            "cost_basis_lamports": COST_BASIS,
            "opened_ts_utc": DAY1 + "T10:00:00Z",
        },
        DAY1 + "T10:00:00Z",
    )
    _append(
        store,
        "MarkToMarket",
        {
            "source": "paper",
            "ts_source": "curve",
            "cash_lamports": INITIAL + BUY_CASH,
            "equity_lamports": INITIAL + BUY_CASH + MARK_LAMPORTS,
            "unrealized_lamports": MARK_LAMPORTS - COST_BASIS,
            "prices_json": json.dumps(
                {MINT: {"mtm_lamports": MARK_LAMPORTS, "spot": "0.00005", "source": "curve"}}
            ),
        },
        DAY1 + "T12:00:00Z",
    )


def _day2_events(store: LedgerStore) -> None:
    _append(
        store,
        "FillRecorded",
        _fill("sell", SELL_CASH, SELL_CASH, 0, 0),
        DAY2 + "T09:00:00Z",
    )
    _append(
        store,
        "PositionClosed",
        {
            "source": "paper",
            "mint": MINT,
            "price_exit": "0.00006",
            "proceeds_lamports": SELL_CASH,
            "realized_pnl_lamports": REALIZED,
            "reason": "take_profit",
        },
        DAY2 + "T09:00:00Z",
    )


def _ledger(path: Path, *, day2: bool) -> Path:
    ledger = path / "ledger.sqlite"
    store = LedgerStore(ledger)
    try:
        store.set_meta("initial_equity_lamports", str(INITIAL))
        _day1_events(store)
        if day2:
            _day2_events(store)
    finally:
        store.close()
    return ledger


def test_funded_account_day_one_starts_from_initial_equity(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, day2=False)
    day1 = DailyReport.build(ledger, DAY1)
    assert day1.equity_start_lamports == INITIAL
    assert day1.equity_start_lamports > 0
    assert day1.equity_end_lamports == INITIAL + BUY_CASH + MARK_LAMPORTS
    assert day1.realized_lamports == 0
    assert day1.unrealized_lamports == MARK_LAMPORTS - COST_BASIS
    assert day1.fees_venue_lamports == BUY_FEES
    assert day1.trades == 1


def test_day_boundaries_chain_across_days(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, day2=True)
    day1 = DailyReport.build(ledger, DAY1)
    day2 = DailyReport.build(ledger, DAY2)
    assert day2.equity_start_lamports == day1.equity_end_lamports
    assert day2.equity_end_lamports == INITIAL + BUY_CASH + SELL_CASH
    assert day2.realized_lamports == REALIZED
    assert day2.unrealized_lamports == 0
    assert day2.closed == 1


def test_rerendering_past_day_ignores_later_trades(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, day2=False)
    before = DailyReport.build(ledger, DAY1)
    before_body = render_daily(before)
    store = LedgerStore(ledger)
    try:
        _day2_events(store)
    finally:
        store.close()
    after = DailyReport.build(ledger, DAY1)
    assert after == before
    assert render_daily(after) == before_body


def test_day_report_on_empty_ledger_has_no_balances(tmp_path: Path) -> None:
    model = DailyReport.build(tmp_path / "var" / "ledger.sqlite", DAY1)
    assert model.equity_start_lamports == 0
    assert model.equity_end_lamports == 0
    assert model.unrealized_lamports == 0
    assert not (tmp_path / "var").exists()


def test_absent_initial_equity_meta_falls_back_to_risk_budget(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    store = LedgerStore(ledger)
    try:
        _day1_events(store)
        assert store.get_meta("initial_equity_lamports") is None
    finally:
        store.close()
    budget_equity = RiskBudget().paper_equity_lamports
    model = DailyReport.build(ledger, DAY1)
    assert model.equity_start_lamports == budget_equity
    assert model.equity_end_lamports == budget_equity + BUY_CASH + MARK_LAMPORTS
