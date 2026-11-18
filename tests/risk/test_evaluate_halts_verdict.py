"""S-B2: evaluate_halts raises on a corrupt ledger and names an already-active halt."""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.engine import RiskEngine

START = 1_790_000_000.0
EQUITY = 10_000_000_000


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _engine(store: LedgerStore, clock: FixtureClock) -> RiskEngine:
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(11)),
        clock=clock,
        autonomy="autonomous-paper",
        env={},
    )


def _append_halt(store: LedgerStore, clock: FixtureClock) -> None:
    payload: dict[str, Any] = {
        "source": "paper",
        "reason": "manual",
        "detail": "operator",
        "equity_lamports": EQUITY,
        "day_start_equity_lamports": EQUITY,
        "set_by": "risk_engine",
    }
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key="halt|manual",
        type="HaltSet",
        payload=payload,
    )


def _tamper(store: LedgerStore) -> LedgerStore:
    """Simulate at-rest tampering below the append-only triggers."""
    db_path_str = str(store.path)
    store.close()
    raw = sqlite3.connect(db_path_str)
    try:
        raw.execute("DROP TRIGGER IF EXISTS events_append_only_u;")
        raw.execute("UPDATE events SET payload_json = '{\"tampered\": true}' WHERE seq = 1;")
        raw.commit()
    finally:
        raw.close()
    return LedgerStore(db_path_str)


def test_evaluate_halts_raises_on_a_corrupt_ledger(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _append_halt(store, clock)
    store = _tamper(store)
    try:
        with pytest.raises(LedgerInconsistent):
            _engine(store, clock).evaluate_halts()
    finally:
        store.close()


def test_evaluate_halts_names_an_already_active_halt(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _append_halt(store, clock)
        assert _engine(store, clock).evaluate_halts() == "already_active"
        assert len(store.read(types=["HaltSet"], limit=None)) == 1
    finally:
        store.close()
