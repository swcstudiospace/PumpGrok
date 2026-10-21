"""RISK-003: breaker thresholds, cooldowns, probes, resets, ledger rebuild."""

from __future__ import annotations

import random
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.breakers import (
    BreakerSet,
    DataStaleBreaker,
    ExecErrorsBreaker,
    LossVelocityBreaker,
)
from pumpgrok.risk.engine import RiskEngine

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT_A = "So11111111111111111111111111111111111111112"
MINT_B = "So22222222222222222222222222222222222222222"


class ManualClock:
    """Callable clock the tests advance by hand."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now_value = start

    def __call__(self) -> float:
        return self.now_value

    def advance(self, seconds: float) -> None:
        self.now_value += seconds


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _engine(store: LedgerStore, clock: FixtureClock, seed: int = 5) -> RiskEngine:
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(seed)),
        clock=clock,
        autonomy="autonomous-paper",
        get_reserves=lambda _mint: (42_000_000_000, 764_000_000_000_000),
    )


def _buy(clock: FixtureClock, ids: IdFactory, mint: str = MINT_A) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=mint,
        side="buy",
        decision_id=ids.ulid(),
        size_lamports=200_000_000,
        max_slippage_bps=50,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )


def _reject_row(store: LedgerStore, clock: FixtureClock, reason: str, n: int) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"rej-{n}",
        type="OrderRejected",
        payload={
            "source": "paper",
            "order_id": f"ord-{n}",
            "decision_id": f"dec-{n}",
            "reason": reason,
            "detail": "seeded",
            "stage": "ACCEPTED",
            "fees_lamports": 0,
        },
    )


def test_data_stale_trips_on_misses() -> None:
    clock = ManualClock()
    breaker = DataStaleBreaker(clock)
    breaker.note_tick(0.0)
    breaker.note_miss(1.0)
    breaker.note_miss(2.0)
    assert breaker.state == "closed"
    breaker.note_miss(3.0)
    assert breaker.state == "open"


def test_data_stale_cooldown_probe_and_reset() -> None:
    clock = ManualClock()
    breaker = DataStaleBreaker(clock)
    breaker.note_tick(0.0)
    breaker.evaluate(120.0)
    assert breaker.is_open
    clock.advance(61.0)
    assert breaker.is_open is False
    assert breaker.state == "half-open"
    assert breaker.admit_probe() is True
    assert breaker.admit_probe() is False
    breaker.resolve_probe(True)
    assert breaker.state == "half-open"
    breaker.note_tick(61.0)
    breaker.note_tick(62.0)
    breaker.note_tick(63.0)
    assert breaker.state == "closed"


def test_data_stale_probe_failure_reopens() -> None:
    clock = ManualClock()
    breaker = DataStaleBreaker(clock)
    breaker.note_tick(0.0)
    breaker.evaluate(120.0)
    clock.advance(61.0)
    assert breaker.admit_probe() is True
    trips = breaker.trips
    breaker.resolve_probe(False)
    assert breaker.state == "open"
    assert breaker.trips == trips + 1


def test_loss_velocity_trips_on_fast_drop() -> None:
    clock = ManualClock()
    breaker = LossVelocityBreaker(clock)
    breaker.note_equity(0.0, EQUITY)
    breaker.note_equity(900.0, int(EQUITY * 0.97))
    assert breaker.evaluate(900.0) == "open"


def test_loss_velocity_ignores_small_drop() -> None:
    clock = ManualClock()
    breaker = LossVelocityBreaker(clock)
    breaker.note_equity(0.0, EQUITY)
    breaker.note_equity(900.0, int(EQUITY * 0.995))
    assert breaker.evaluate(900.0) == "closed"


def test_loss_velocity_resets_when_calm() -> None:
    clock = ManualClock()
    breaker = LossVelocityBreaker(clock)
    breaker.note_equity(0.0, EQUITY)
    breaker.note_equity(900.0, int(EQUITY * 0.97))
    assert breaker.evaluate(900.0) == "open"
    clock.advance(1800.0)
    now = clock()
    breaker.note_equity(now - 300.0, int(EQUITY * 0.97))
    breaker.note_equity(now, int(EQUITY * 0.969))
    assert breaker.evaluate(now) == "closed"


def test_exec_errors_trips_on_qualifying_rejects() -> None:
    clock = ManualClock()
    breaker = ExecErrorsBreaker(clock)
    breaker.note_reject(0.0, "tx_dropped")
    breaker.note_reject(60.0, "slippage_exceeded")
    assert breaker.state == "closed"
    breaker.note_reject(120.0, "rpc_error")
    assert breaker.state == "open"


def test_exec_errors_ignores_other_reasons_and_window() -> None:
    clock = ManualClock()
    breaker = ExecErrorsBreaker(clock)
    breaker.note_reject(0.0, "approval_missing")
    breaker.note_reject(1.0, "seat_may_trade")
    assert breaker.state == "closed"
    breaker.note_reject(0.0, "tx_dropped")
    breaker.note_reject(700.0, "tx_dropped")
    assert breaker.state == "closed"


def test_breaker_set_refresh_appends_trip_once(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        for n, reason in enumerate(("tx_dropped", "slippage_exceeded", "rpc_error")):
            _reject_row(store, clock, reason, n)
        made = BreakerSet(store, clock)
        made.refresh(
            ts_utc=format_ts_utc(START), source="paper", correlation_id="t", equity_now=EQUITY
        )
        assert made.open_breakers() == ["exec_errors"]
        trips = store.read(types=["BreakerTripped"], limit=None)
        assert len(trips) == 1
        assert trips[0]["payload"]["breaker"] == "exec_errors"
        made.refresh(
            ts_utc=format_ts_utc(START), source="paper", correlation_id="t", equity_now=EQUITY
        )
        assert len(store.read(types=["BreakerTripped"], limit=None)) == 1
    finally:
        store.close()


def test_breaker_set_rebuild_survives_restart(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        for n in range(3):
            _reject_row(store, clock, "tx_dropped", n)
        first = BreakerSet(store, clock)
        first.refresh(
            ts_utc=format_ts_utc(START), source="paper", correlation_id="t", equity_now=EQUITY
        )
        assert first.open_breakers() == ["exec_errors"]
        second = BreakerSet.rebuild(store, clock)
        assert second.open_breakers() == ["exec_errors"]
        clock.advance_to(START + 901.0)
        assert second.open_breakers() == []
        assert second.half_open_breakers() == ["exec_errors"]
    finally:
        store.close()


def test_engine_probe_flow(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(5))
    try:
        engine = _engine(store, clock)
        for n in range(3):
            engine.note_miss(
                START + float(n),
                ts_utc=format_ts_utc(START + n),
                source="paper",
                correlation_id="t",
            )
        assert engine.check(_buy(clock, ids), seat="bot-04-sniper").reason == "breaker_open"
        clock.advance_to(START + 63.0)
        first = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert first.passed is True
        assert first.probe is True
        second = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert second.passed is False
        assert second.reason == "breaker_open"
        engine.resolve_probe("data_stale", False, source="paper", correlation_id="t")
        third = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert third.passed is False
        assert third.reason == "breaker_open"
    finally:
        store.close()
