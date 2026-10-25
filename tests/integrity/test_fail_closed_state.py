"""INT-02: corrupt or missing ledger, equity, and peak inputs fail closed.

Each of the three former silent fallbacks raises ``CorruptState`` instead of
substituting a default (old peak, zero equity, empty genesis). Deterministic,
no network: the reducer folds in memory, the seat and shutdown paths run on a
fixture clock against a scratch ledger.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.core.errors import CorruptState
from pumpgrok.ledger.reducer import initial_state, reduce
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.supervisor.lifecycle import shutdown
from pumpgrok.supervisor.scheduler import ROSTER, Supervisor
from pumpgrok.supervisor.seat_task import SeatContext, SeatTask, append_escalation

MINT = "TESTMINT"
EQUITY = 10_000_000_000


def _store(tmp_path: Path, name: str = "ledger.sqlite") -> LedgerStore:
    path = tmp_path / name
    recreate_ledger_db(path)
    return LedgerStore(str(path))


async def _ok(ctx: SeatContext) -> dict[str, Any]:
    return {"ok": True}


def _opened(seq: int, ts_utc: str) -> dict[str, Any]:
    return {
        "type": "PositionOpened",
        "payload": {"mint": MINT, "price_entry": "100", "token_units": 10},
        "seq": seq,
        "ts_utc": ts_utc,
        "correlation_id": "test",
    }


def _mark(seq: int, ts_utc: str, spot: str) -> dict[str, Any]:
    return {
        "type": "MarkToMarket",
        "payload": {"prices_json": json.dumps({MINT: {"spot": spot}})},
        "seq": seq,
        "ts_utc": ts_utc,
        "correlation_id": "test",
    }


def test_corrupt_mtm_spot_raises_instead_of_keeping_old_peak() -> None:
    """A corrupt mark spot raises; a valid one still moves the peak."""
    ts_utc = "2026-10-21T00:00:00+00:00"
    state = initial_state(source="paper", initial_equity_lamports=EQUITY, day_utc="2026-10-21")
    state = reduce(state, _opened(1, ts_utc))
    marked = reduce(state, _mark(2, ts_utc, "150"))
    assert marked.positions[MINT].price_peak == Decimal("150")
    with pytest.raises(CorruptState, match="refusing to keep the old peak"):
        reduce(state, _mark(2, ts_utc, "bogus"))


def test_missing_and_corrupt_seat_equity_meta_raise(tmp_path: Path) -> None:
    """The seat records its equity; it never invents a zero default."""
    clock = FixtureClock(start=1_000.0)
    store = _store(tmp_path)
    try:
        task = SeatTask(
            "bot-04-sniper",
            1.0,
            _ok,
            clock=clock,
            rng=make_rng(11),
            store=store,
        )
        with pytest.raises(CorruptState, match="is missing"):
            task._initial_equity()
        store.set_meta("initial_equity_lamports", "not-a-number")
        with pytest.raises(CorruptState, match="corrupt initial_equity"):
            task._initial_equity()
        store.set_meta("initial_equity_lamports", str(EQUITY))
        assert task._initial_equity() == EQUITY
    finally:
        store.close()


def _supervisor(store: LedgerStore, clock: FixtureClock) -> Supervisor:
    return Supervisor(store=store, clock=clock, rng=make_rng(11), cycles=dict.fromkeys(ROSTER, _ok))


async def test_missing_genesis_equity_meta_raises_at_shutdown(tmp_path: Path) -> None:
    """Shutdown snapshots the recorded equity; a missing meta raises."""
    clock = FixtureClock(start=5_000.0)
    store = _store(tmp_path, "missing.sqlite")
    try:
        append_escalation(
            store,
            clock,
            kind="probe",
            seat="bot-04-sniper",
            detail="probe",
            source="paper",
            correlation_id="test",
        )
        supervisor = _supervisor(store, clock)
        with pytest.raises(CorruptState, match="initial_equity_lamports meta is missing"):
            await shutdown(
                supervisor,
                store=store,
                health_path=str(tmp_path / "health.json"),
                journal_dir=str(tmp_path / "journal"),
                trades_path=str(tmp_path / "trades.jsonl"),
            )
    finally:
        store.close()


async def test_empty_ledger_without_meta_raises_at_shutdown(tmp_path: Path) -> None:
    """An empty ledger with no recorded equity is not a zero-equity genesis."""
    clock = FixtureClock(start=5_000.0)
    store = _store(tmp_path, "empty.sqlite")
    try:
        supervisor = _supervisor(store, clock)
        with pytest.raises(CorruptState, match="initial_equity_lamports meta is missing"):
            await shutdown(
                supervisor,
                store=store,
                health_path=str(tmp_path / "health.json"),
                journal_dir=str(tmp_path / "journal"),
                trades_path=str(tmp_path / "trades.jsonl"),
            )
    finally:
        store.close()


async def test_recorded_genesis_equity_shuts_down_cleanly(tmp_path: Path) -> None:
    """Positive control: with the meta recorded, shutdown still exits 0."""
    clock = FixtureClock(start=5_000.0)
    store = _store(tmp_path, "recorded.sqlite")
    try:
        store.set_meta("initial_equity_lamports", str(EQUITY))
        supervisor = _supervisor(store, clock)
        code = await shutdown(
            supervisor,
            store=store,
            health_path=str(tmp_path / "health.json"),
            journal_dir=str(tmp_path / "journal"),
            trades_path=str(tmp_path / "trades.jsonl"),
        )
        assert code == 0
        snapshots = store.read_snapshots()
        assert len(snapshots) == 1
        body = snapshots[0]["state"]
        assert int(body["day_start_equity_lamports"]) == EQUITY
    finally:
        store.close()
