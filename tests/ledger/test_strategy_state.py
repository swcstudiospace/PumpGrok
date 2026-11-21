"""STR-03: ledger-backed per-strategy open state."""

from __future__ import annotations

from pathlib import Path

from pumpgrok.ledger.strategy_state import read_open_positions, record_close, record_open
from pumpgrok.ledger.store import LedgerStore


def _open_store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(str(tmp_path / "ledger.sqlite"))


def test_open_close_round_trip(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        record_open(
            store,
            strategy_id="momentum_breakout",
            mint="MintA",
            entry_price_lamports=1000,
            ts_utc="2026-01-01T00:00:00Z",
            source="paper",
            correlation_id="strat-state-1",
        )
        record_open(
            store,
            strategy_id="momentum_breakout",
            mint="MintB",
            entry_price_lamports=2000,
            ts_utc="2026-01-01T00:01:00Z",
            source="paper",
            correlation_id="strat-state-2",
        )
        assert read_open_positions(store, "momentum_breakout") == [
            {"strategy_id": "momentum_breakout", "mint": "MintA", "entry_price_lamports": 1000},
            {"strategy_id": "momentum_breakout", "mint": "MintB", "entry_price_lamports": 2000},
        ]
        record_close(
            store,
            strategy_id="momentum_breakout",
            mint="MintA",
            ts_utc="2026-01-01T00:02:00Z",
            source="paper",
            correlation_id="strat-state-3",
        )
        assert read_open_positions(store, "momentum_breakout") == [
            {"strategy_id": "momentum_breakout", "mint": "MintB", "entry_price_lamports": 2000},
        ]
    finally:
        store.close()


def test_positions_are_per_strategy(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        record_open(
            store,
            strategy_id="mean_reversion",
            mint="MintA",
            entry_price_lamports=500,
            ts_utc="2026-01-01T00:00:00Z",
            source="paper",
            correlation_id="strat-state-4",
        )
        assert read_open_positions(store, "momentum_breakout") == []
        assert len(read_open_positions(store, "mean_reversion")) == 1
    finally:
        store.close()
