"""Daily/weekly report rendering from a fixture ledger (PAPER-006).

Snapshot pins the summary and trades sections; the whole document must be
ASCII-only; templates use str.format only (no jinja2).
"""

from __future__ import annotations

from pathlib import Path

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.reporting.daily import DailyReport
from pumpgrok.reporting.render import field_names, render_daily, render_weekly
from pumpgrok.reporting.weekly import WeeklyReport

DAY = "2026-10-20"
MINT = "So11111111111111111111111111111111111111112"
CID = "01J0000000000000000000000"


def _append(store: LedgerStore, seq: int, type: str, payload: dict, ts: str) -> None:
    store.append(
        ts_utc=ts,
        source="paper",
        correlation_id=CID,
        idempotency_key=f"test-{type}-{seq}",
        type=type,
        payload=payload,
    )


def build_fixture_ledger(path: Path) -> Path:
    """Append a deterministic event set covering every report section."""
    ledger = path / "ledger.sqlite"
    store = LedgerStore(ledger)
    try:
        _append(
            store,
            1,
            "FillRecorded",
            {
                "source": "paper",
                "order_id": "ord-1",
                "decision_id": "dec-1",
                "side": "buy",
                "mint": MINT,
                "filled_lamports": 200000000,
                "filled_units": 3579186000000,
                "filled_fraction": "1",
                "price_avg": "0.00005587",
                "venue_fee_lamports": 2000000,
                "network_cost_lamports": 9000,
                "cash_delta_lamports": -200009000,
                "venue_tx_ref": "dry_run:test-1",
            },
            DAY + "T10:00:00Z",
        )
        _append(
            store,
            2,
            "PositionOpened",
            {
                "source": "paper",
                "mint": MINT,
                "price_entry": "0.00005587",
                "token_units": 3579186000000,
                "cost_basis_lamports": 200009000,
                "opened_ts_utc": DAY + "T10:00:00Z",
                "ticket_id": "SOL-20261020-001",
            },
            DAY + "T10:00:00Z",
        )
        _append(
            store,
            3,
            "MarkToMarket",
            {
                "source": "paper",
                "ts_source": "curve",
                "cash_lamports": 9799991000,
                "equity_lamports": 9996002000,
                "unrealized_lamports": -4007000,
            },
            DAY + "T12:00:00Z",
        )
        _append(
            store,
            4,
            "OrderRejected",
            {
                "source": "paper",
                "order_id": "ord-2",
                "decision_id": "dec-2",
                "reason": "slippage_exceeded",
                "detail": "confirm 3512285 < threshold 3560247",
                "stage": "CONFIRMING",
                "fees_lamports": 9000,
            },
            DAY + "T13:00:00Z",
        )
        _append(
            store,
            5,
            "JournalNote",
            {
                "source": "paper",
                "seat": "rug",
                "note_kind": "verdict",
                "text": "CLEAR evidence ok",
                "refs": [],
            },
            DAY + "T14:00:00Z",
        )
        _append(
            store,
            6,
            "PositionClosed",
            {
                "source": "paper",
                "mint": MINT,
                "price_exit": "0.00005800",
                "proceeds_lamports": 203000000,
                "realized_pnl_lamports": 2991000,
                "reason": "take_profit",
                "pnl_pct": "1.49",
                "hold_seconds": 7200,
                "venue_tx_ref": "dry_run:test-6",
            },
            DAY + "T15:00:00Z",
        )
    finally:
        store.close()
    return ledger


def test_daily_snapshot_pins_summary_and_trades(tmp_path: Path) -> None:
    ledger = build_fixture_ledger(tmp_path)
    model = DailyReport.build(ledger, DAY)
    body = render_daily(model)
    body.encode("ascii")
    assert "# PumpGrok paper report - daily - 2026-10-20 (UTC)" in body
    assert "## Summary" in body
    assert "trades (buys/sells): 1 | closed: 1 | win rate: 1" in body
    assert "## Trades" in body
    assert "SOL-20261020-001" not in body  # closed row carries mint + reason
    assert "take_profit" in body
    assert "slippage_exceeded | 1" in body
    assert "CLEAR | 1" in body
    for section in field_names():
        assert f"## {section}" in body


def test_daily_uses_no_jinja2_and_ascii_only(tmp_path: Path) -> None:
    ledger = build_fixture_ledger(tmp_path)
    body = render_daily(DailyReport.build(ledger, DAY))
    assert "jinja" not in body.lower()
    assert "{{" not in body and "{%" not in body
    assert body.encode("ascii")


def test_weekly_adds_per_day_and_live_gate(tmp_path: Path) -> None:
    ledger = build_fixture_ledger(tmp_path)
    body = render_weekly(WeeklyReport.build(ledger, DAY, root=tmp_path))
    body.encode("ascii")
    assert "## Per day" in body
    assert "2026-10-20 | fills 1 | closed 1 | rejected 1 | events 6" in body
    assert "## Live gate" in body
    for gate_id in (
        "mode_live",
        "live_enable_env",
        "min_paper_days",
        "performance_thresholds",
        "wallet_allowlist",
        "notional_cap",
        "confirmation_record",
        "adapter_registered",
        "no_active_stop",
    ):
        assert gate_id in body


def test_empty_ledger_renders_without_creating_files(tmp_path: Path) -> None:
    missing = tmp_path / "var" / "ledger.sqlite"
    body = render_daily(DailyReport.build(missing, DAY))
    body.encode("ascii")
    assert "## Summary" in body
    assert not missing.exists()
    assert not (tmp_path / "var").exists()
