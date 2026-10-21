"""RISK-002/RISK-004/RISK-005: halts, kill switch, KILL tokens (plan 04-05)."""

from __future__ import annotations

import random
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest
from pydantic import ValidationError

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.killswitch import (
    ClearRefused,
    InflightBarrier,
    KillSwitch,
    kill_file_text,
    parse_kill_line,
)
from pumpgrok.tools.risk.halt_status import HaltStatusIn, build_halt_status_tool
from pumpgrok.tools.risk.kill_switch import KillSwitchIn, build_kill_switch_tool

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT_A = "So11111111111111111111111111111111111111112"
MINT_B = "So22222222222222222222222222222222222222222"


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _engine(store: LedgerStore, clock: FixtureClock, seed: int = 7, **kwargs: Any) -> RiskEngine:
    kwargs.setdefault("get_reserves", lambda _mint: (42_000_000_000, 764_000_000_000_000))
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(seed)),
        clock=clock,
        autonomy="autonomous-paper",
        **kwargs,
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


def _sell(clock: FixtureClock, ids: IdFactory, mint: str = MINT_A) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=mint,
        side="sell",
        decision_id=ids.ulid(),
        token_units=3_000_000,
        max_slippage_bps=50,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )


def _position(store: LedgerStore, clock: FixtureClock, mint: str, units: int, basis: int) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"pos-{mint[-4:]}",
        type="PositionOpened",
        payload={
            "source": "paper",
            "mint": mint,
            "price_entry": "0.00001",
            "token_units": units,
            "cost_basis_lamports": basis,
            "opened_ts_utc": format_ts_utc(clock.now()),
            "symbol": "TST",
            "creator": "Creator1111111111111111111111111111111111",
            "ticket_id": TICKET,
            "score": "0.8",
        },
    )


def _human_approval(clock: FixtureClock, ids: IdFactory, kind: str) -> ApprovalRecord:
    return ApprovalRecord(
        id=f"apr-{ids.ulid()}",
        kind=kind,  # type: ignore[arg-type]
        approved_by="human:alice",
        raw_message="human clear",
        at=datetime.fromtimestamp(clock.now(), UTC),
    )


def test_parse_kill_line_shapes() -> None:
    assert parse_kill_line("KILL operator stop") == (False, "operator stop")
    assert parse_kill_line("KILL FLATTEN close all") == (True, "close all")
    assert parse_kill_line("KILLX nope") is None
    assert parse_kill_line("KILL") is None
    assert parse_kill_line("kill lower") is None
    assert parse_kill_line("") is None
    assert kill_file_text("halt now", False) == "halt now"
    assert kill_file_text("close all", True) == "FLATTEN close all"


def test_kill_sources_precedence(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    killswitch = tmp_path / "KILLSWITCH"
    try:
        ks = KillSwitch(
            clock,
            store=store,
            killswitch_path=killswitch,
            alert_lines=lambda: ["KILL alert reason"],
            env={},
        )
        assert ks.poll().active is True
        assert ks.poll().source == "alert_command"
        killswitch.write_text("file reason", encoding="utf-8")
        assert ks.poll() == ks.poll()
        assert ks.poll().source == "file"
        ks_env = KillSwitch(
            clock,
            store=store,
            killswitch_path=killswitch,
            alert_lines=lambda: ["KILL alert reason"],
            env={"PUMPGROK_KILLSWITCH": "1"},
        )
        assert ks_env.poll().source == "env"
        assert ks.poll().source == "file"
    finally:
        store.close()


def test_alert_source_observed_to_ledger(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ks = KillSwitch(clock, store=store, alert_lines=lambda: ["KILL FLATTEN go flat"], env={})
        row = ks.observe(ts_utc=format_ts_utc(START), source="paper", correlation_id="t")
        assert row is not None
        assert row["payload"]["origin"] == "alert_command"
        assert row["payload"]["flatten_requested"] is True
        assert ks.observe(ts_utc=format_ts_utc(START), source="paper", correlation_id="t") is None
        assert len(store.read(types=["KillSwitchSet"], limit=None)) == 1
    finally:
        store.close()


def test_engine_kill_blocks_buys_not_flatten(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    try:
        killswitch = tmp_path / "KILLSWITCH"
        killswitch.write_text("operator stop", encoding="utf-8")
        engine = _engine(store, clock, killswitch_path=killswitch)
        assert engine.check(_buy(clock, ids), seat="bot-04-sniper").reason == "kill_switch"
        assert len(store.read(types=["KillSwitchSet"], limit=None)) == 1
        flat = engine.check(_sell(clock, ids), seat="bot-04-sniper", exit_reason="kill_flatten")
        assert flat.passed is True
    finally:
        store.close()


def test_clear_refused_while_live_then_accepted(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    killswitch = tmp_path / "KILLSWITCH"
    try:
        killswitch.write_text("operator stop", encoding="utf-8")
        ks = KillSwitch(clock, store=store, killswitch_path=killswitch, env={})
        assert ks.poll().active is True
        with pytest.raises(ClearRefused):
            ks.request_clear(
                _human_approval(clock, ids, "killswitch_clear"),
                "all clear",
                ts_utc=format_ts_utc(START),
            )
        with pytest.raises(ClearRefused):
            ks.request_clear(
                _human_approval(clock, ids, "halt_clear"), "wrong kind", ts_utc=format_ts_utc(START)
            )
        killswitch.unlink()
        ks.request_clear(
            _human_approval(clock, ids, "killswitch_clear"),
            "all clear",
            ts_utc=format_ts_utc(START),
        )
        assert ks.poll().active is False
        assert len(store.read(types=["KillSwitchCleared"], limit=None)) == 1
        approvals = store.read(types=["ApprovalRecorded"], limit=None)
        assert any(p["payload"]["kind"] == "killswitch_clear" for p in approvals)
        with pytest.raises(ClearRefused):
            ks_env = KillSwitch(clock, store=store, env={"PUMPGROK_KILLSWITCH": "1"})
            ks_env.request_clear(
                _human_approval(clock, ids, "killswitch_clear"), "x", ts_utc=format_ts_utc(START)
            )
    finally:
        store.close()


def test_clear_refused_for_seat_signature(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    try:
        ks = KillSwitch(clock, store=store, env={})
        seat_approval = ApprovalRecord(
            id=f"apr-{ids.ulid()}",
            kind="killswitch_clear",
            approved_by="human:bot-04-sniper",
            raw_message="forged",
            at=datetime.fromtimestamp(clock.now(), UTC),
        )
        with pytest.raises(ClearRefused):
            ks.request_clear(seat_approval, "x", ts_utc=format_ts_utc(START))
    finally:
        store.close()


async def test_kill_switch_tool_writes_file_and_rejects_clear(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    killswitch = tmp_path / "KILLSWITCH"
    try:
        tool = build_kill_switch_tool(store, clock, killswitch)
        out = await tool(KillSwitchIn(action="set", reason="tool stop"))
        assert out.active is True
        assert killswitch.read_text(encoding="utf-8") == "tool stop"
        flat = await tool(KillSwitchIn(action="flatten_request", reason="close all"))
        assert flat.flatten_requested is True
        assert killswitch.read_text(encoding="utf-8") == "FLATTEN close all"
        with pytest.raises(ValidationError):
            KillSwitchIn(action="clear", reason="x")  # type: ignore[arg-type]
    finally:
        store.close()


def test_halt_latches_and_clears_only_via_human(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    try:
        store.append(
            ts_utc=format_ts_utc(START),
            source="paper",
            correlation_id="t",
            idempotency_key="fill-loss",
            type="FillRecorded",
            payload={
                "source": "paper",
                "order_id": "o",
                "decision_id": "d",
                "side": "sell",
                "mint": MINT_A,
                "filled_lamports": 0,
                "filled_units": 0,
                "filled_fraction": "1",
                "price_avg": "0.00001",
                "venue_fee_lamports": 0,
                "network_cost_lamports": 0,
                "cash_delta_lamports": -600_000_000,
                "latency_s": "1.0",
                "venue_tx_ref": "",
            },
        )
        engine = _engine(store, clock)
        assert engine.check(_buy(clock, ids), seat="bot-04-sniper").reason == "daily_loss_halt"
        # seat-signed approvals refuse: human prefix forged with a seat id
        seat = ApprovalRecord(
            id=f"apr-{ids.ulid()}",
            kind="halt_clear",
            approved_by="human:bot-02-risk",
            raw_message="forged",
            at=datetime.fromtimestamp(clock.now(), UTC),
        )
        with pytest.raises(ValueError):
            engine.request_halt_clear(seat, "x")
        clock.advance_to(START + 86400.0)
        assert engine.check(_buy(clock, ids), seat="bot-04-sniper").reason == "halted"
        engine.request_halt_clear(_human_approval(clock, ids, "halt_clear"), "reviewed")
        assert engine.check(_buy(clock, ids), seat="bot-04-sniper").passed is True
        assert len(store.read(types=["HaltCleared"], limit=None)) == 1
    finally:
        store.close()


def test_kill_verdict_blocks_mint_for_all_seats(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    try:
        engine = _engine(store, clock)
        engine.record_kill_verdict(MINT_A, "rug evidence")
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert decision.passed is False
        assert decision.reason == "breaker_open"
        other = engine.check(_buy(clock, ids, MINT_B), seat="bot-04-sniper")
        assert other.passed is True
        manual = engine.check(_sell(clock, ids), seat="bot-06-exit", exit_reason="rug_alert")
        assert manual.passed is True
    finally:
        store.close()


def test_flatten_plan_closes_every_position(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _position(store, clock, MINT_A, 1_000_000, 100_000_000)
        _position(store, clock, MINT_B, 2_000_000, 200_000_000)
        engine = _engine(store, clock)
        plan = engine.plan_flatten()
        assert len(plan) == 2
        assert {o.order.mint for o in plan} == {MINT_A, MINT_B}
        for item in plan:
            assert item.order.side.value == "sell"
            assert item.approval.approved_by == "risk_engine"
            decision = engine.check(item.order, seat="bot-06-exit", exit_reason="kill_flatten")
            assert decision.passed is True
    finally:
        store.close()


def test_inflight_barrier_waits_for_drain() -> None:
    barrier = InflightBarrier()
    barrier.register("a")
    barrier.register("b")
    assert len(barrier) == 2
    done = threading.Event()

    def _drain() -> None:
        time.sleep(0.05)
        barrier.done("a")
        barrier.done("b")
        done.set()

    worker = threading.Thread(target=_drain)
    worker.start()
    assert barrier.wait_empty(timeout_s=5.0) is True
    worker.join()
    assert done.is_set()
    assert barrier.wait_empty(timeout_s=0.1) is True


async def test_halt_status_reports_breaker(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        store.append(
            ts_utc=format_ts_utc(START),
            source="paper",
            correlation_id="t",
            idempotency_key="trip-1",
            type="BreakerTripped",
            payload={
                "source": "paper",
                "breaker": "data_stale",
                "metric": "m",
                "threshold": "t",
                "cooldown_s": 60,
            },
        )
        tool = build_halt_status_tool(store, None, clock)
        out = await tool(HaltStatusIn())
        assert out.breaker_open is True
        assert out.halted is True
    finally:
        store.close()
