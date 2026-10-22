"""Weekly totals cover the whole Monday-to-Sunday week, not only Sunday.

Regression for the review finding that WeeklyReport copied profit, fees, win
rate and trade rows from the Sunday daily report. The reporting week is the
ISO week starting Monday (weekly.py ``_iso_monday``, paper-engine 8.1).
"""

from __future__ import annotations

from pathlib import Path

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.reporting.render import render_weekly
from pumpgrok.reporting.weekly import WeeklyReport

INITIAL = 1_000_000_000
MON = "2026-10-19"
TUE = "2026-10-20"
SUN = "2026-10-25"
NEXT_MON = "2026-10-26"
MINT = "So11111111111111111111111111111111111111112"
CID = "01J0000000000000000000000"
BUY_CASH = -200_009_000
COST_BASIS = 200_009_000
SELL_CASH = 205_000_000
REALIZED = SELL_CASH - COST_BASIS


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


def _ledger(path: Path) -> Path:
    """Monday opens and buys; Tuesday sells at a profit; nothing Wednesday to Sunday."""
    ledger = path / "ledger.sqlite"
    store = LedgerStore(ledger)
    try:
        store.set_meta("initial_equity_lamports", str(INITIAL))
        _append(
            store,
            "FillRecorded",
            _fill("buy", 200_000_000, BUY_CASH, 2_000_000, 9_000),
            MON + "T10:00:00Z",
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
                "opened_ts_utc": MON + "T10:00:00Z",
            },
            MON + "T10:00:00Z",
        )
        _append(
            store,
            "FillRecorded",
            _fill("sell", SELL_CASH, SELL_CASH, 0, 0),
            TUE + "T15:00:00Z",
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
            TUE + "T15:00:00Z",
        )
    finally:
        store.close()
    return ledger


def test_weekly_realized_results_come_from_the_whole_week(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    week = WeeklyReport.build(ledger, "2026-10-21", root=tmp_path)
    assert week.period == "weekly"
    assert week.closed == 1
    assert week.realized_lamports == REALIZED
    assert week.win_rate == "1"
    assert week.trades == 2
    assert week.fees_venue_lamports == 2_009_000
    assert len(week.trade_rows) == 1
    assert week.trade_rows[0].pnl_lamports == REALIZED


def test_weekly_balances_span_monday_open_to_sunday_close(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    week = WeeklyReport.build(ledger, MON, root=tmp_path)
    assert week.equity_start_lamports == INITIAL
    assert week.equity_end_lamports == INITIAL + BUY_CASH + SELL_CASH


def test_sunday_input_resolves_to_the_same_monday_week(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    from_sunday = WeeklyReport.build(ledger, SUN, root=tmp_path)
    from_monday = WeeklyReport.build(ledger, MON, root=tmp_path)
    assert from_sunday.day == from_monday.day == "2026-10-19 to 2026-10-25"
    assert from_sunday.realized_lamports == from_monday.realized_lamports == REALIZED
    assert from_sunday.equity_end_lamports == from_monday.equity_end_lamports
    assert from_sunday.trades == from_monday.trades == 2


def test_next_week_excludes_previous_week_results(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    week = WeeklyReport.build(ledger, NEXT_MON, root=tmp_path)
    assert week.closed == 0
    assert week.trades == 0
    assert week.realized_lamports == 0
    assert week.equity_start_lamports == INITIAL + BUY_CASH + SELL_CASH
    assert week.equity_end_lamports == INITIAL + BUY_CASH + SELL_CASH


def test_per_day_table_keeps_each_day_in_the_week(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    body = render_weekly(WeeklyReport.build(ledger, MON, root=tmp_path))
    assert "2026-10-19 | fills 1 | closed 0 | rejected 0 | events 2" in body
    assert "2026-10-20 | fills 1 | closed 1 | rejected 0 | events 2" in body
    assert "2026-10-25 | fills 0 | closed 0 | rejected 0 | events 0" in body


def test_fractional_monday_midnight_fill_belongs_to_its_week(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    store = LedgerStore(ledger)
    try:
        store.set_meta("initial_equity_lamports", str(INITIAL))
        for ts in ("2026-10-18T23:59:59.999999Z", MON + "T00:00:00.500000Z"):
            store.append(
                ts_utc=ts,
                source="paper",
                correlation_id=CID,
                idempotency_key=f"fill-{ts}",
                type="FillRecorded",
                payload=_fill("buy", 100_000_000, -100_001_000, 1_000, 0),
            )
    finally:
        store.close()
    week = WeeklyReport.build(ledger, MON, root=tmp_path)
    previous = WeeklyReport.build(ledger, "2026-10-12", root=tmp_path)
    assert week.trades == 1
    assert previous.trades == 1
    body = render_weekly(week)
    assert "2026-10-19 | fills 1 |" in body
