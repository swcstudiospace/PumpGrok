"""RSK-04: live failure classes trip exec_errors and any UNKNOWN sets a halt.

Transient classes (send failure, RPC error, confirmation timeout) count
toward the existing exec_errors threshold; any UNKNOWN trips at once,
writes a ledger halt row, and is never retried (no second send frame).
"""

from __future__ import annotations

import random
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.breakers import BreakerSet, LIVE_FAILURE_CLASSES
from pumpgrok.risk.engine import RiskEngine

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _halt_rows(store: LedgerStore) -> list[dict[str, object]]:
    return [e for e in store.read(types=["HaltSet"], limit=None) if isinstance(e.get("payload"), dict)]


def test_live_failure_taxonomy_is_the_four_classes() -> None:
    assert LIVE_FAILURE_CLASSES == frozenset(
        {"send_failure", "rpc_error", "unknown", "confirmation_timeout"}
    )


def test_transient_classes_trip_exec_errors_at_threshold(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    breakers = BreakerSet(store, clock)
    for index, cls in enumerate(["send_failure", "rpc_error", "confirmation_timeout"]):
        halted = breakers.note_live_failure(
            cls, clock.now() + index, ts_utc=format_ts_utc(clock.now()), source="paper", correlation_id="test"
        )
        assert halted is False
    assert "exec_errors" in breakers.open_breakers()


def test_unknown_sets_a_halt_and_trips_at_once(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    breakers = BreakerSet(store, clock)
    halts: list[bool] = []
    halted = breakers.note_live_failure(
        "unknown",
        clock.now(),
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        on_unknown_halt=lambda **_kw: halts.append(True),
    )
    assert halted is True
    assert halts == [True]
    assert "exec_errors" in breakers.open_breakers()


def test_engine_unknown_writes_a_ledger_halt_row_once(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(11)),
        clock=clock,
        autonomy="autonomous-paper",
    )
    halted = engine.note_live_failure("unknown")
    assert halted is True
    rows = _halt_rows(store)
    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert isinstance(payload, dict)
    assert payload.get("reason") == "exec_unknown"
    # A second UNKNOWN is never retried: no second halt row is written.
    again = engine.note_live_failure("unknown")
    assert again is True
    assert len(_halt_rows(store)) == 1


def test_engine_transients_do_not_halt(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(11)),
        clock=clock,
        autonomy="autonomous-paper",
    )
    for cls in ["send_failure", "rpc_error"]:
        assert engine.note_live_failure(cls) is False
    assert _halt_rows(store) == []
