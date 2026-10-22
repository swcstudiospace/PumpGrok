"""INV-R-01..03: kill switch halts within one cycle, flatten, human-only clear."""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.errors import OrderRejectedError, OrderUnknownError
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc, parse_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.killswitch import ClearRefused, KillSwitch, kill_file_text
from pumpgrok.tools.risk.kill_switch import KillSwitchIn

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT_A = "So11111111111111111111111111111111111111112"
MINT_B = "So22222222222222222222222222222222222222222"
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
        ids=IdFactory(clock, random.Random(7)),
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
        size_lamports=SIZE,
        max_slippage_bps=50,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )


def _snap(mint: str = MINT_A) -> CurveSnapshot:
    return CurveSnapshot(mint=mint, s_lamports=S0, t_units=T0)


class _ScriptedCurves:
    """Pop one scripted snapshot per read; hold the last."""

    def __init__(self, reads: list[CurveSnapshot]) -> None:
        self._reads = list(reads)

    async def curve(self, mint: str) -> CurveSnapshot | None:
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


def _adapter(
    store: LedgerStore, clock: FixtureClock, engine: RiskEngine, ids: IdFactory
) -> PaperAdapter:
    return PaperAdapter(
        store=store,
        risk=engine,
        ids=ids,
        clock=clock,
        rng=make_rng(7),
        budget=RiskBudget(),
        price_source=_ScriptedCurves([_snap(), _snap()]),
        p_drop=0.0,
    )


async def _drive(coro: Any, clock: FixtureClock) -> Any:
    task = asyncio.create_task(coro)
    for _ in range(400):
        if task.done():
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    return await task


def _position(store: LedgerStore, clock: FixtureClock, mint: str, units: int) -> None:
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
            "cost_basis_lamports": units,
            "opened_ts_utc": format_ts_utc(clock.now()),
            "symbol": "TST",
            "creator": "Creator1111111111111111111111111111111111",
            "ticket_id": TICKET,
            "score": "0.8",
        },
    )


def _clear_approval(clock: FixtureClock, ids: IdFactory, by: str) -> ApprovalRecord:
    return ApprovalRecord(
        id=f"apr-{ids.ulid()}",
        kind="killswitch_clear",
        approved_by=by,
        raw_message="clearing",
        at=datetime.fromtimestamp(clock.now(), UTC),
    )


@pytest.mark.parametrize("source", ["env_at_start", "file", "alert"])
async def test_kill_switch_halts_within_one_cycle(tmp_path: Path, source: str) -> None:
    """INV-R-01: env/file/alert engagement rejects buys within one 5 s cycle."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(7))
        kill_file = tmp_path / "KILLSWITCH"
        if source == "env_at_start":
            engine = _engine(store, clock, env={"PUMPGROK_KILLSWITCH": "stop"})
            origin = "env"
        elif source == "file":
            kill_file.write_text("operator stop", encoding="utf-8")
            engine = _engine(store, clock, killswitch_path=kill_file)
            origin = "file"
        else:
            engine = _engine(store, clock, alert_lines=lambda: ["KILL operator stop"])
            origin = "alert_command"
        adapter = _adapter(store, clock, engine, ids)
        for step in range(2):
            clock.advance_to(START + 5.0 * step)
            with pytest.raises(OrderRejectedError) as excinfo:
                await _drive(adapter.place(_buy(clock, ids), seat="bot-04-sniper"), clock)
            assert excinfo.value.reason == "kill_switch"
        sets = store.read(types=["KillSwitchSet"], limit=None)
        assert len(sets) == 1
        assert sets[0]["payload"]["origin"] == origin
        assert sets[0]["payload"]["source"] == "paper"
        set_ts = parse_ts_utc(str(sets[0]["ts_utc"]))
        fills = store.read(types=["FillRecorded"], limit=None)
        buys_after = [
            fill
            for fill in fills
            if str(fill["payload"].get("side")) == "buy"
            and parse_ts_utc(str(fill["ts_utc"])) > set_ts
        ]
        assert buys_after == []
    finally:
        store.close()


async def test_in_flight_order_rejected_at_confirming(tmp_path: Path) -> None:
    """INV-R-01: an ACCEPTED order is rejected, never filled, when the file lands mid-flight."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(7))
        kill_file = tmp_path / "KILLSWITCH"
        engine = _engine(store, clock, killswitch_path=kill_file)
        adapter = _adapter(store, clock, engine, ids)
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
        kill_file.write_text("operator stop", encoding="utf-8")
        for _ in range(400):
            if task.done():
                break
            clock.advance_to(clock.now() + 1.0)
            await asyncio.sleep(0)
        assert task.done()
        err = task.exception()
        assert isinstance(err, OrderRejectedError)
        assert not isinstance(err, OrderUnknownError)
        assert err.reason == "kill_switch"
        assert err.stage == "CONFIRMING"
        assert store.read(types=["FillRecorded"], limit=None) == []
        rejects = store.read(types=["OrderRejected"], limit=None)
        assert rejects != []
        assert rejects[-1]["payload"]["reason"] == "kill_switch"
        assert rejects[-1]["payload"]["stage"] == "CONFIRMING"
    finally:
        store.close()


async def test_kill_flatten_closes_every_position(tmp_path: Path) -> None:
    """INV-R-02: flatten waits on the barrier, then closes each position once."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(7))
        _position(store, clock, MINT_A, 3_000_000)
        _position(store, clock, MINT_B, 4_000_000)
        kill_file = tmp_path / "KILLSWITCH"
        kill_file.write_text(kill_file_text("close all", True), encoding="utf-8")
        engine = _engine(store, clock, killswitch_path=kill_file)
        adapter = _adapter(store, clock, engine, ids)
        plans = engine.plan_flatten(correlation_id="test")
        assert {plan.order.mint for plan in plans} == {MINT_A, MINT_B}
        for plan in plans:
            assert plan.order.side == "sell"
            fill = await _drive(
                adapter.place(plan.order, seat="bot-02-risk", exit_reason="kill_flatten"),
                clock,
            )
            assert fill.status.value == "filled"
        closed = store.read(types=["PositionClosed"], limit=None)
        assert {(row["payload"]["mint"], row["payload"]["reason"]) for row in closed} == {
            (MINT_A, "kill_flatten"),
            (MINT_B, "kill_flatten"),
        }
        placed = store.read(types=["OrderPlaced"], limit=None)
        sells_a = [row for row in placed if row["payload"].get("mint") == MINT_A]
        sells_b = [row for row in placed if row["payload"].get("mint") == MINT_B]
        assert len(sells_a) == 1
        assert len(sells_b) == 1
    finally:
        store.close()


def test_kill_switch_clear_requires_human_and_clear_sources(tmp_path: Path) -> None:
    """INV-R-03: clear is CLI-only and human-only; refused while any source persists."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(7))
        kill_file = tmp_path / "KILLSWITCH"
        kill_file.write_text("operator stop", encoding="utf-8")
        switch = KillSwitch(clock, store=store, killswitch_path=kill_file, env={})
        with pytest.raises(ValidationError):
            KillSwitchIn(action="clear", reason="x")
        # A seat-signed clear never constructs: the schema demands human:.
        with pytest.raises(ValidationError):
            _clear_approval(clock, ids, "bot-02-risk")
        with pytest.raises(ClearRefused):
            switch.request_clear(
                _clear_approval(clock, ids, "human:alice"),
                "human clear while set",
                ts_utc=format_ts_utc(clock.now()),
                source="paper",
                correlation_id="test",
            )
        kill_file.unlink()
        switch.request_clear(
            _clear_approval(clock, ids, "human:alice"),
            "all clear",
            ts_utc=format_ts_utc(clock.now()),
            source="paper",
            correlation_id="test",
        )
        cleared = store.read(types=["KillSwitchCleared"], limit=None)
        assert len(cleared) == 1
        recorded = store.read(types=["ApprovalRecorded"], limit=None)
        assert [row["payload"]["kind"] for row in recorded] == ["killswitch_clear"]
        engine = _engine(store, clock, killswitch_path=kill_file)
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert decision.passed is True
    finally:
        store.close()
