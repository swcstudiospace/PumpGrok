"""Report figures come from the ledger: the daily loss is measured against start equity,
the halt budget comes from RiskBudget, a closed trade's basis and P&L percent come from
the figures its row records, and a figure the ledger does not track is never printed as zero.

Regressions for the events sweep findings on the daily figures.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from pumpgrok.core.errors import CorruptState
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.reporting.daily import DailyReport
from pumpgrok.reporting.render import render_daily

INITIAL = 1_000_000_000
DAY = "2026-10-20"
MINT = "So11111111111111111111111111111111111111112"
CID = "01J0000000000000000000000"
BUY_CASH = -200_009_000
COST_BASIS = 200_009_000


def _append(store: LedgerStore, type: str, payload: dict, ts: str) -> None:
    store.append(
        ts_utc=ts,
        source="paper",
        correlation_id=CID,
        idempotency_key=f"{type}-{ts}",
        type=type,
        payload=payload,
    )


def _buy_and_mark(path: Path, mark: int) -> Path:
    """Start with INITIAL, buy a position at COST_BASIS, then mark it at ``mark``."""
    ledger = path / "ledger.sqlite"
    store = LedgerStore(ledger)
    try:
        store.set_meta("initial_equity_lamports", str(INITIAL))
        _append(
            store,
            "FillRecorded",
            {
                "source": "paper",
                "order_id": "ord-buy",
                "decision_id": "dec-buy",
                "side": "buy",
                "mint": MINT,
                "filled_lamports": 200_000_000,
                "filled_units": 1000,
                "filled_fraction": "1",
                "price_avg": "0.00005",
                "venue_fee_lamports": 2_000_000,
                "network_cost_lamports": 9_000,
                "cash_delta_lamports": BUY_CASH,
            },
            DAY + "T10:00:00Z",
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
                "opened_ts_utc": DAY + "T10:00:00Z",
            },
            DAY + "T10:00:00Z",
        )
        _append(
            store,
            "MarkToMarket",
            {
                "source": "paper",
                "ts_source": "curve",
                "cash_lamports": INITIAL + BUY_CASH,
                "equity_lamports": INITIAL + BUY_CASH + mark,
                "unrealized_lamports": mark - COST_BASIS,
                "prices_json": json.dumps(
                    {MINT: {"mtm_lamports": mark, "spot": "0.00005", "source": "curve"}}
                ),
            },
            DAY + "T12:00:00Z",
        )
    finally:
        store.close()
    return ledger


def _raw_event(ledger: Path, *, seq: int, ts: str, type: str, payload: dict) -> None:
    """Write a row the store would refuse, as a tampered or legacy ledger would hold it."""
    db = sqlite3.connect(ledger)
    try:
        db.execute(
            "INSERT INTO events (seq, ts_utc, source, correlation_id, idempotency_key,"
            " type, payload_json, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                seq,
                ts,
                "paper",
                CID,
                f"raw-{seq}",
                type,
                json.dumps(payload),
                "0" * 64,
                f"raw-{seq}",
            ),
        )
        db.commit()
    finally:
        db.close()


def test_daily_loss_is_measured_against_start_equity_and_the_halt_comes_from_risk_budget(
    tmp_path: Path,
) -> None:
    body = render_daily(DailyReport.build(_buy_and_mark(tmp_path / "loss", mark=190_000_000), DAY))
    halt = format(RiskBudget().daily_loss_halt_fraction * 100, ".2f")
    # start 1 SOL; end = cash 0.799991000 SOL + mark 0.190000000 SOL = 0.989991000 SOL
    assert f"daily loss: 1.00 % (halt at {halt} %)" in body


def test_daily_loss_reads_zero_when_equity_rose(tmp_path: Path) -> None:
    report = DailyReport.build(_buy_and_mark(tmp_path / "gain", mark=1_100_000_000), DAY)
    body = render_daily(report)
    assert "daily loss: 0.00 %" in body


def test_closed_trade_uses_the_figures_the_writer_records(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    store = LedgerStore(ledger)
    try:
        _append(
            store,
            "PositionClosed",
            {
                "source": "paper",
                "mint": MINT,
                "price_exit": "0.00006",
                "proceeds_lamports": 203_000_000,
                "realized_pnl_lamports": 2_991_000,
                "reason": "take_profit",
                "pnl_pct": "0.0149",
                "hold_seconds": 7200,
                "venue_tx_ref": "dry_run:x",
            },
            DAY + "T15:00:00Z",
        )
    finally:
        store.close()
    body = render_daily(DailyReport.build(ledger, DAY))
    # basis = proceeds - realized = 0.200009000 SOL; pnl % = 2991000 / 200009000
    assert "| 0.200009000 | take_profit | 0.002991000 | +1.50 | not tracked |" in body


def test_closed_trade_missing_its_proceeds_is_corruption(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    LedgerStore(ledger).close()
    _raw_event(
        ledger,
        seq=100,
        ts=DAY + "T15:00:00Z",
        type="PositionClosed",
        payload={"mint": MINT, "realized_pnl_lamports": 1, "reason": "manual"},
    )
    with pytest.raises(CorruptState, match="proceeds_lamports"):
        DailyReport.build(ledger, DAY)


def test_trade_percent_is_exact_for_large_amounts(tmp_path: Path) -> None:
    basis = 10**20
    realized = 125_000_000_000_000_001
    ledger = tmp_path / "ledger.sqlite"
    store = LedgerStore(ledger)
    try:
        _append(
            store,
            "PositionClosed",
            {
                "source": "paper",
                "mint": MINT,
                "price_exit": "1",
                "proceeds_lamports": basis + realized,
                "realized_pnl_lamports": realized,
                "reason": "take_profit",
            },
            DAY + "T15:00:00Z",
        )
    finally:
        store.close()
    body = render_daily(DailyReport.build(ledger, DAY))
    # 125000000000000001 / 10**20 = 0.125000000000000001, which rounds up to 0.13
    assert "| +0.13 | not tracked |" in body


def test_untracked_network_fees_and_heartbeats_are_not_printed_as_zero(tmp_path: Path) -> None:
    report = DailyReport.build(_buy_and_mark(tmp_path / "untracked", mark=190_000_000), DAY)
    body = render_daily(report)
    assert "+ network not tracked\n" in body
    assert "## Bot health\nnot tracked\n" in body
    assert "network 0.000000000" not in body
