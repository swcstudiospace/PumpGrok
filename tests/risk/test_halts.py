"""INV-R-04..06: daily-loss floor, halt survival across rollover, drawdown halt."""

from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import FLOOR_HALTED_DAILY, RiskEngine, halt_key
from pumpgrok.tools.risk.halt_status import HaltStatusIn, run_halt_status

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT_A = "So11111111111111111111111111111111111111112"
DAY_ONE = "2026-10-21"


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _engine(store: LedgerStore, clock: FixtureClock, **kwargs: Any) -> RiskEngine:
    kwargs.setdefault("get_reserves", lambda _mint: (42_000_000_000, 764_000_000_000_000))
    kwargs.setdefault("env", {})
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(11)),
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


def _fill(store: LedgerStore, clock: FixtureClock, ids: IdFactory, cash_delta: int) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"fill-{ids.ulid()}",
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
            "cash_delta_lamports": cash_delta,
            "latency_s": "1.0",
            "venue_tx_ref": "",
        },
    )


def _rollover(store: LedgerStore, clock: FixtureClock) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"rollover-{format_ts_utc(clock.now())[:10]}",
        type="DailyRollover",
        payload={
            "source": "paper",
            "day_utc": format_ts_utc(clock.now())[:10],
            "day_start_equity_lamports": EQUITY,
            "prior_day_json": "{}",
            "open_positions": [],
        },
    )


def test_daily_loss_halt_floor(tmp_path: Path) -> None:
    """INV-R-04: 5 % loss trips HaltSet once per day with exact constitution bytes."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(11))
        _fill(store, clock, ids, cash_delta=-600_000_000)
        engine = _engine(store, clock)
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert decision.reason == "daily_loss_halt"
        halts = store.read(types=["HaltSet"], limit=None)
        assert len(halts) == 1
        assert halts[0]["payload"]["detail"] == FLOOR_HALTED_DAILY
        assert halts[0]["payload"]["detail"].encode() == b"FLOOR HALTED \xe2\x80\x93 DAILY LOSS LIMIT"
        assert halts[0]["idempotency_key"] == halt_key("daily_loss", DAY_ONE)
        assert halts[0]["idempotency_key"] == hashlib.sha256(
            b"HaltSet|daily_loss|2026-10-21"
        ).hexdigest()
        repeat = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert repeat.reason == "halted"
        assert len(store.read(types=["HaltSet"], limit=None)) == 1
    finally:
        store.close()


async def test_halt_survives_utc_rollover_until_human_clear(tmp_path: Path) -> None:
    """INV-R-05: rollover resets counters but never clears; only human clear releases."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(11))
        _fill(store, clock, ids, cash_delta=-600_000_000)
        engine = _engine(store, clock)
        assert engine.check(_buy(clock, ids), seat="bot-04-sniper").reason == "daily_loss_halt"
        clock.advance_to(START + 86_400.0)
        _rollover(store, clock)
        assert engine.check(_buy(clock, ids), seat="bot-04-sniper").reason == "halted"
        status = await run_halt_status(HaltStatusIn(), store, None, clock)
        assert status["halted"] is True
        assert status["daily_loss_halt"] is True
        from pumpgrok.core.approvals import ApprovalRecord

        bot_clear = None
        try:
            bot_clear = ApprovalRecord(
                id=f"apr-{ids.ulid()}",
                kind="halt_clear",
                approved_by="bot-02-risk",
                raw_message="bot clear",
                at=datetime.fromtimestamp(clock.now(), UTC),
            )
        except Exception:
            bot_clear = None
        assert bot_clear is None
        human = ApprovalRecord(
            id=f"apr-{ids.ulid()}",
            kind="halt_clear",
            approved_by="human:alice",
            raw_message="all clear",
            at=datetime.fromtimestamp(clock.now(), UTC),
        )
        engine.request_halt_clear(human, "all clear")
        cleared = store.read(types=["HaltCleared"], limit=None)
        assert len(cleared) == 1
        assert cleared[0]["payload"]["cleared_by"] == "human:alice"
        status = await run_halt_status(HaltStatusIn(), store, None, clock)
        assert status["halted"] is False
        assert engine.check(_buy(clock, ids), seat="bot-04-sniper").passed is True
    finally:
        store.close()


def test_drawdown_halt(tmp_path: Path) -> None:
    """INV-R-06: 15 % peak-to-equity drawdown trips HaltSet(drawdown); peak persists."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(11))
        _fill(store, clock, ids, cash_delta=2_000_000_000)
        _fill(store, clock, ids, cash_delta=-2_000_000_000)
        engine = _engine(store, clock)
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert decision.passed is False
        assert decision.reason == "drawdown_halt"
        halts = store.read(types=["HaltSet"], limit=None)
        assert len(halts) == 1
        assert halts[0]["payload"]["reason"] == "drawdown"
        clock.advance_to(START + 86_400.0)
        _rollover(store, clock)
        assert engine.check(_buy(clock, ids), seat="bot-04-sniper").reason == "halted"
    finally:
        store.close()
