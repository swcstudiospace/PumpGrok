"""INV-R-12: single-send - an unknown result is never retried, approval consumed."""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.approvals import parse_human_phrase, record_human_approval
from pumpgrok.core.errors import OrderRejectedError, OrderUnknownError
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.limits import EngineLimits

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT = "So11111111111111111111111111111111111111112"
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


class _ScriptedCurves:
    def __init__(self, reads: list[CurveSnapshot]) -> None:
        self._reads = list(reads)

    async def curve(self, mint: str) -> CurveSnapshot | None:
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


async def test_unknown_result_never_retried(tmp_path: Path) -> None:
    """INV-R-12: confirmation timeout yields UNKNOWN once; repeats replay it, approval consumed."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(7))
        engine = RiskEngine(
            store=store,
            budget=RiskBudget(),
            ids=IdFactory(clock, random.Random(7)),
            clock=clock,
            autonomy="manual-ticket",
            get_reserves=lambda _mint: (S0, T0),
            env={},
        )
        snap = CurveSnapshot(mint=MINT, s_lamports=S0, t_units=T0)
        adapter = PaperAdapter(
            store=store,
            risk=engine,
            ids=ids,
            clock=clock,
            rng=make_rng(7),
            budget=RiskBudget(),
            limits=EngineLimits(confirm_timeout_s=0.001),
            price_source=_ScriptedCurves([snap, snap]),
            p_drop=0.0,
        )
        approval_id = f"apr-{ids.ulid()}"
        record = parse_human_phrase(
            f"approve {TICKET} {MINT} 0.2 100",
            kind="human_buy",
            by="human:alice",
            approval_id=approval_id,
            at=datetime.fromtimestamp(clock.now(), UTC),
        )
        record_human_approval(
            store, record, ts_utc=format_ts_utc(clock.now()), source="paper", correlation_id="test"
        )

        def order(decision_id: str, approval: str = approval_id) -> OrderRequest:
            return OrderRequest(
                ticket_id=TICKET,
                mint=MINT,
                side="buy",
                decision_id=decision_id,
                size_lamports=SIZE,
                max_slippage_bps=100,
                approval_id=approval,
                correlation_id="test",
            )

        async def drive(coro: Any) -> Any:
            task = asyncio.create_task(coro)
            for _ in range(400):
                if task.done():
                    break
                clock.advance_to(clock.now() + 1.0)
                await asyncio.sleep(0)
            return await task

        first_decision = ids.ulid()
        with pytest.raises(OrderUnknownError) as excinfo:
            await drive(adapter.place(order(first_decision), seat="bot-04-sniper"))
        assert "outcome UNKNOWN; never retried" in excinfo.value.detail
        placed = store.read(types=["OrderPlaced"], limit=None)
        assert len(placed) == 1
        consumed = [
            row
            for row in store.read(types=["ApprovalRecorded"], limit=None)
            if row["payload"].get("consumed") is True
        ]
        assert len(consumed) == 1
        assert consumed[0]["payload"]["id"] == approval_id
        with pytest.raises(OrderUnknownError):
            await drive(adapter.place(order(first_decision), seat="bot-04-sniper"))
        assert len(store.read(types=["OrderPlaced"], limit=None)) == 1
        with pytest.raises(OrderRejectedError) as missing:
            await drive(adapter.place(order(ids.ulid()), seat="bot-04-sniper"))
        assert missing.value.reason == "approval_missing"
        assert len(store.read(types=["OrderPlaced"], limit=None)) == 1
    finally:
        store.close()
