"""RT-04: exit deadlines are re-armed from ledger rows, not from memory.

A desk that crashes and restarts re-arms every open position's exit
deadline from the PositionOpened stamp; deadlines move only with the
ledger, never with process memory.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.supervisor.recovery import recover

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
MINT = "So11111111111111111111111111111111111111112"


def test_exit_deadlines_rearmed_from_ledger_rows(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", "10000000000")
    store.set_meta("source", "paper")
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key="open-1",
        type="PositionOpened",
        payload={
            "source": "paper",
            "mint": MINT,
            "price_entry": "0.00001",
            "token_units": 3_000_000,
            "cost_basis_lamports": 100_000_000,
            "opened_ts_utc": format_ts_utc(clock.now()),
            "symbol": "TST",
            "creator": "Creator1111111111111111111111111111111111",
            "ticket_id": "SOL-20260201-001",
            "score": "0.8",
        },
    )
    clock.jump(600.0)
    # A fresh desk (new engine state) recovers the same deadline from the row.
    restored = recover(store, clock, max_hold_s=3600.0)
    assert restored.deadlines[MINT] == START + 3600.0
    assert restored.deadlines[MINT] > clock.now()
