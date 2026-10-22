"""INV-R-09: breaker lifecycle, restart survival, CONFIRMING re-check."""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.errors import OrderRejectedError
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.breakers import BREAKER_NAMES, BreakerSet, breaker_trip_key
from pumpgrok.risk.engine import RiskEngine

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT_A = "So11111111111111111111111111111111111111112"
S0 = 42_000_000_000
T0 = 764_000_000_000_000
SIZE = 200_000_000


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _engine(store: LedgerStore, clock: FixtureClock, **kwargs: Any) -> RiskEngine:
    kwargs.setdefault("get_reserves", lambda _mint: (S0, T0))
    kwargs.setdefault("env", {})
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(31)),
        clock=clock,
        autonomy="autonomous-paper",
        **kwargs,
    )


def _buy(clock: FixtureClock, ids: IdFactory) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=MINT_A,
        side="buy",
        decision_id=ids.ulid(),
        size_lamports=SIZE,
        max_slippage_bps=50,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )


def _append(store: LedgerStore, clock: FixtureClock, type: str, payload: dict[str, Any]) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"seed-{store.count() + 1}",
        type=type,
        payload=payload,
    )


def _mtm(equity: int) -> dict[str, Any]:
    return {
        "source": "paper",
        "ts_source": "curve",
        "cash_lamports": equity,
        "equity_lamports": equity,
        "unrealized_lamports": 0,
        "prices_json": "{}",
    }


def _reject_row(clock: FixtureClock, ids: IdFactory) -> dict[str, Any]:
    return {
        "source": "paper",
        "order_id": ids.ulid(),
        "decision_id": ids.ulid(),
        "reason": "tx_dropped",
        "detail": "seeded drop",
        "stage": "CONFIRMING",
    }


def _trip_payload(name: str) -> dict[str, Any]:
    return {
        "source": "paper",
        "breaker": name,
        "metric": "seeded",
        "threshold": "seeded",
        "cooldown_s": 60,
    }


def _fill_for_velocity(store: LedgerStore, clock: FixtureClock, ids: IdFactory) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"vel-{store.count() + 1}",
        type="FillRecorded",
        payload={
            "source": "paper",
            "order_id": ids.ulid(),
            "decision_id": ids.ulid(),
            "side": "sell",
            "mint": MINT_A,
            "filled_lamports": 0,
            "filled_units": 0,
            "filled_fraction": "1",
            "price_avg": "0.00001",
            "venue_fee_lamports": 0,
            "network_cost_lamports": 0,
            "cash_delta_lamports": -300_000_000,
            "latency_s": "1.0",
            "venue_tx_ref": "",
        },
    )


def _trip(store: LedgerStore, clock: FixtureClock, ids: IdFactory, name: str) -> None:
    """Drive the domain trip condition for one breaker through the engine."""
    engine = _engine(store, clock)
    if name == "data_stale":
        for _ in range(3):
            engine.note_miss(
                clock.now(),
                ts_utc=format_ts_utc(clock.now()),
                source="paper",
                correlation_id="test",
            )
    elif name == "loss_velocity":
        _append(store, clock, "MarkToMarket", _mtm(EQUITY))
        clock.advance_to(clock.now() + 50.0)
        _fill_for_velocity(store, clock, ids)
        clock.advance_to(clock.now() + 50.0)
        _append(store, clock, "MarkToMarket", _mtm(9_700_000_000))
    elif name == "exec_errors":
        for _ in range(3):
            _append(store, clock, "OrderRejected", _reject_row(clock, ids))
    decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
    assert decision.passed is False
    assert decision.reason == "breaker_open"


def _cooldown(name: str) -> float:
    return {"data_stale": 60.0, "loss_velocity": 1800.0, "exec_errors": 900.0}[name]


@pytest.mark.parametrize("breaker", ["data_stale", "loss_velocity", "exec_errors"])
def test_breaker_lifecycle(tmp_path: Path, breaker: str) -> None:
    """INV-R-09: closed -> open -> half-open -> closed|open with idempotent edges."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(31))
        engine = _engine(store, clock)
        assert engine._breakers.by_name(breaker).state == "closed"
        _trip(store, clock, ids, breaker)
        trips = store.read(types=["BreakerTripped"], limit=None)
        assert len(trips) == 1
        assert trips[0]["payload"]["breaker"] == breaker
        assert trips[0]["idempotency_key"] == breaker_trip_key(breaker, 1)
        refused = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert refused.passed is False
        assert refused.reason == "breaker_open"
        assert {row["id"]: row["status"] for row in refused.evaluated}["breaker_open"] == "fail"
        assert len(store.read(types=["BreakerTripped"], limit=None)) == 1
        rebuilt = BreakerSet.rebuild(store, FixtureClock(start=clock.now()))
        assert rebuilt.by_name(breaker).is_open is True
        clock.advance_to(clock.now() + _cooldown(breaker) + 1.0)
        probe = engine._breakers.by_name(breaker)
        # Threshold-1 breakers (loss_velocity) report "closed" once the
        # cooldown expires, but the half-open flag is set either way.
        assert probe.state in ("half-open", "closed")
        assert probe.half_open is True
        assert engine._breakers.admit_probe(breaker) is True
        assert engine._breakers.admit_probe(breaker) is False
        engine._breakers.resolve_probe(
            breaker,
            False,
            ts_utc=format_ts_utc(clock.now()),
            source="paper",
            correlation_id="test",
        )
        assert engine._breakers.by_name(breaker).state == "open"
        # A failed probe re-opens with a fresh cooldown; that re-open is a trip row,
        # so a restart after it cannot shorten the cooldown (R24).
        assert len(store.read(types=["BreakerTripped"], limit=None)) == 2
        clock.advance_to(clock.now() + _cooldown(breaker) + 1.0)
        post = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert post.passed is True
        for _ in range(5):
            current = engine._breakers.by_name(breaker)
            if current.state == "closed":
                break
            if current.probe_inflight:
                engine.resolve_probe(breaker, True, source="paper", correlation_id="test")
                continue
            assert engine._breakers.admit_probe(breaker) is True
            engine._breakers.resolve_probe(
                breaker,
                True,
                ts_utc=format_ts_utc(clock.now()),
                source="paper",
                correlation_id="test",
            )
        assert engine._breakers.by_name(breaker).state == "closed"
        resets = store.read(types=["BreakerReset"], limit=None)
        if breaker == "loss_velocity":
            # Threshold-1 expiry converges to closed without a reset
            # transition (no half-open probe cycle); trip idempotency above
            # is this breaker's edge guarantee.
            assert resets == []
        else:
            assert len(resets) == 1
            assert resets[0]["payload"]["breaker"] == breaker
    finally:
        store.close()


def test_breaker_names_match_r34_vocabulary() -> None:
    assert list(BREAKER_NAMES) == ["data_stale", "loss_velocity", "exec_errors"]


class _ScriptedCurves:
    def __init__(self, reads: list[CurveSnapshot]) -> None:
        self._reads = list(reads)

    async def curve(self, mint: str) -> CurveSnapshot | None:
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


async def _drive(coro: Any, clock: FixtureClock) -> Any:
    task = asyncio.create_task(coro)
    for _ in range(400):
        if task.done():
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    return await task


async def test_breaker_rechecked_at_confirming(tmp_path: Path) -> None:
    """INV-R-09: a trip between ACCEPTED and the fill refuses at CONFIRMING."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(31))
        engine = _engine(store, clock)
        snap = CurveSnapshot(mint=MINT_A, s_lamports=S0, t_units=T0)
        adapter = PaperAdapter(
            store=store,
            risk=engine,
            ids=ids,
            clock=clock,
            rng=make_rng(31),
            budget=RiskBudget(),
            price_source=_ScriptedCurves([snap, snap]),
            p_drop=0.0,
        )
        task = asyncio.create_task(adapter.place(_buy(clock, ids), seat="bot-04-sniper"))
        for _ in range(400):
            if task.done():
                break
            if store.read(types=["OrderPlaced"], limit=None):
                break
            clock.advance_to(clock.now() + 1.0)
            await asyncio.sleep(0)
        assert store.read(types=["OrderPlaced"], limit=None) != []
        assert not task.done()
        _append(store, clock, "BreakerTripped", _trip_payload("data_stale"))
        for _ in range(400):
            if task.done():
                break
            clock.advance_to(clock.now() + 1.0)
            await asyncio.sleep(0)
        assert task.done()
        err = task.exception()
        assert isinstance(err, OrderRejectedError)
        assert err.reason == "breaker_open"
        assert err.stage == "CONFIRMING"
        trips = store.read(types=["BreakerTripped"], limit=None)
        assert [row["payload"]["breaker"] for row in trips] == ["data_stale"]
        assert store.read(types=["FillRecorded"], limit=None) == []
    finally:
        store.close()
