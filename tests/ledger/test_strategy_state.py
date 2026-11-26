<<<<<<< HEAD
"""STR-03: ledger-backed per-strategy open state."""

from __future__ import annotations

from pathlib import Path

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.strategy_state import read_open_positions, record_close, record_open


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
=======
"""STR-03: strategy_state round-trips one JSON snapshot per strategy, hashed and replaceable.

The snapshot holds integer lamports and epoch timestamps (floats), so it uses a sorted JSON
form that allows floats but refuses NaN and infinity. The stored hash covers the exact
bytes, and a row altered outside the API is refused on read.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from pumpgrok.ledger import strategy_state
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.strategy_state import StrategyStateError


def _store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(str(tmp_path / "ledger.sqlite"))


def test_snapshot_round_trips_per_strategy(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        state = {"peak_lamports": 5_000_000, "tape": {"ts": 1.5, "price_lamports": 7}}
        strategy_state.write_state(store, "momentum_breakout", state)
        assert strategy_state.read_state(store, "momentum_breakout") == state
        assert strategy_state.read_state(store, "mean_reversion") is None
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
    finally:
        store.close()


<<<<<<< HEAD
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
=======
def test_second_write_replaces_the_first(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    store = LedgerStore(str(path))
    try:
        strategy_state.write_state(store, "momentum_breakout", {"peak_lamports": 1})
        strategy_state.write_state(store, "momentum_breakout", {"peak_lamports": 2})
        assert strategy_state.read_state(store, "momentum_breakout") == {"peak_lamports": 2}
    finally:
        store.close()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM strategy_state").fetchone()[0] == 1


def test_hash_is_sha256_of_the_canonical_json(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        digest = strategy_state.write_state(store, "s", {"b": 2, "a": 1})
        expected = hashlib.sha256(b'{"a":1,"b":2}').hexdigest()
        assert digest == expected
        assert strategy_state.state_hash(store, "s") == expected
    finally:
        store.close()


def test_nan_and_infinity_are_refused(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        with pytest.raises(ValueError):
            strategy_state.write_state(store, "s", {"ts": float("nan")})
        with pytest.raises(ValueError):
            strategy_state.write_state(store, "s", {"ts": float("inf")})
        assert strategy_state.read_state(store, "s") is None
    finally:
        store.close()


def test_altered_row_is_refused_on_read(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    store = LedgerStore(str(path))
    try:
        strategy_state.write_state(store, "s", {"peak_lamports": 1})
        with sqlite3.connect(path) as db:
            db.execute(
                "UPDATE strategy_state SET state_json = ? WHERE strategy_id = ?",
                (json.dumps({"peak_lamports": 999}), "s"),
            )
        with pytest.raises(StrategyStateError):
            strategy_state.read_state(store, "s")
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
    finally:
        store.close()
