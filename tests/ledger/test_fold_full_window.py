"""Regression: full-ledger folds see events past the 1000th row.

LedgerStore.read orders ASC with a default limit of 200. The five full-ledger
folds (kill switch, halt status, exposure, pnl, render report) must pass
``limit=None`` so a KillSwitchSet or trade appended after the 1000th event is
still visible instead of failing open on a truncated window.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.journal.render_report import RenderReportIn, run_render_report
from pumpgrok.tools.portfolio.exposure import ExposureIn, run_exposure
from pumpgrok.tools.portfolio.pnl import PnlIn, run_pnl
from pumpgrok.tools.risk.halt_status import HaltStatusIn, run_halt_status
from pumpgrok.tools.risk.kill_switch import _status

START = 1469918176.385
FILLERS = 1005
EXPO_MINT = "ExpoLate1111111111111111111111111111111111"
PNL_MINT = "PnlLate11111111111111111111111111111111111"


def _append(store: LedgerStore, seq: int, type: str, payload: dict) -> None:
    store.append(
        ts_utc="2026-01-01T00:00:00.000001Z",
        source="paper",
        correlation_id="01J0000000000000000000000",
        idempotency_key=f"fold-window-{seq:06d}",
        type=type,
        payload=payload,
    )


def _build_store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    for i in range(FILLERS):
        _append(
            store,
            i,
            "JournalNote",
            {"source": "paper", "seat": "desk", "note_kind": "note", "text": "filler"},
        )
    base = FILLERS
    _append(
        store,
        base,
        "KillSwitchSet",
        {
            "source": "paper",
            "origin": "tool",
            "reason": "regression",
            "flatten_requested": False,
            "set_by": "test",
        },
    )
    _append(
        store,
        base + 1,
        "PositionOpened",
        {
            "source": "paper",
            "mint": EXPO_MINT,
            "price_entry": "1",
            "token_units": 10,
            "cost_basis_lamports": 5000,
            "opened_ts_utc": "2026-01-02T00:00:00Z",
        },
    )
    _append(
        store,
        base + 2,
        "PositionOpened",
        {
            "source": "paper",
            "mint": PNL_MINT,
            "price_entry": "1",
            "token_units": 10,
            "cost_basis_lamports": 5000,
            "opened_ts_utc": "2026-01-02T00:00:00Z",
        },
    )
    _append(
        store,
        base + 3,
        "FillRecorded",
        {
            "source": "paper",
            "order_id": "o1",
            "decision_id": "d1",
            "side": "buy",
            "mint": PNL_MINT,
            "filled_lamports": 5000,
            "filled_units": 10,
            "filled_fraction": "1",
            "price_avg": "1",
            "venue_fee_lamports": 7,
            "network_cost_lamports": 3,
        },
    )
    _append(
        store,
        base + 4,
        "PositionClosed",
        {
            "source": "paper",
            "mint": PNL_MINT,
            "price_exit": "2",
            "proceeds_lamports": 6000,
            "realized_pnl_lamports": 1000,
            "reason": "take_profit",
        },
    )
    return store


def test_unbounded_read_returns_full_window(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    try:
        assert store.count() == FILLERS + 5
        assert len(store.read()) == 200
        assert len(store.read(limit=None)) == FILLERS + 5
    finally:
        store.close()


def test_kill_switch_sees_set_after_1000th_event(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    try:
        view = _status(store, None, "test", FixtureClock(start=START))
        assert view["active"] is True
        assert view["source"] == "command"
        assert view["reason"] == "regression"
    finally:
        store.close()


async def test_halt_status_reports_kill_switch_after_1000th_event(
    tmp_path: Path,
) -> None:
    store = _build_store(tmp_path)
    try:
        out = await run_halt_status(HaltStatusIn(), store, None, FixtureClock(start=START))
        assert out["halted"] is True
        assert out["kill_switch_active"] is True
        assert "kill_switch" in out["reasons"]
    finally:
        store.close()


async def test_exposure_includes_trade_after_1000th_event(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    try:
        out = await run_exposure(ExposureIn(), store, FixtureClock(start=START))
        by_mint = {row["mint"]: row["exposure_lamports"] for row in out["per_token"]}
        assert by_mint.get(EXPO_MINT) == 5000
        assert out["open_positions"] >= 1
        assert out["gross_exposure_lamports"] >= 5000
    finally:
        store.close()


async def test_pnl_includes_trade_after_1000th_event(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    try:
        out = await run_pnl(PnlIn(window="day"), store, FixtureClock(start=START))
        assert out["trades"] >= 1
        assert out["fees_lamports"] == 10
        assert out["realised_lamports"] == 1000
        assert out["closed_trades"] >= 1
    finally:
        store.close()


async def test_render_report_counts_trade_after_1000th_event(tmp_path: Path) -> None:
    store = _build_store(tmp_path)
    try:
        out = await run_render_report(
            RenderReportIn(period="daily", deliver=False),
            store,
            FixtureClock(start=START),
            tmp_path / "reports",
        )
        assert out["summary"]["trades"] >= 1
        assert out["summary"]["realised_lamports"] == 1000
        assert out["summary"]["open_positions"] >= 1
    finally:
        store.close()
