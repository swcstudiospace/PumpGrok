"""INV-R-10..11: exact-phrase approval, autonomous-paper still checks limits."""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.approvals import ApprovalRecord, parse_human_phrase, record_human_approval
from pumpgrok.core.errors import OrderRejectedError
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.ledger.autonomy import autonomy_rows, read_autonomy
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
STALE_TICKET = "SOL-20260201-002"
MINT = "So11111111111111111111111111111111111111112"
OTHER_MINT = "So22222222222222222222222222222222222222222"
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
    kwargs.setdefault("autonomy", "manual-ticket")
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(41)),
        clock=clock,
        **kwargs,
    )


def _buy(
    clock: FixtureClock, ids: IdFactory, approval_id: str, mint: str = MINT, size: int = SIZE
) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=mint,
        side="buy",
        decision_id=ids.ulid(),
        size_lamports=size,
        max_slippage_bps=100,
        approval_id=approval_id,
        correlation_id="test",
    )


def _sell(
    clock: FixtureClock, ids: IdFactory, approval_id: str, units: int = 3_000_000
) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=MINT,
        side="sell",
        decision_id=ids.ulid(),
        token_units=units,
        max_slippage_bps=100,
        approval_id=approval_id,
        correlation_id="test",
    )


def _approve(
    store: LedgerStore,
    clock: FixtureClock,
    ids: IdFactory,
    phrase: str,
    kind: str = "human_buy",
    by: str = "human:alice",
) -> str:
    approval_id = f"apr-{ids.ulid()}"
    record = parse_human_phrase(
        phrase, kind=kind, by=by, approval_id=approval_id, at=datetime.fromtimestamp(clock.now(), UTC)
    )
    record_human_approval(
        store, record, ts_utc=format_ts_utc(clock.now()), source="paper", correlation_id="test"
    )
    return approval_id


VARIANTS = [
    "exact",
    "wrong_size",
    "wrong_mint",
    "missing_slippage",
    "stale_ticket",
    "bot_approver",
    "exit_without_exit_rule_approval",
]


@pytest.mark.parametrize("variant", VARIANTS)
def test_exact_phrase_required(tmp_path: Path, variant: str) -> None:
    """INV-R-10: only the token-for-token phrase authorises a manual-ticket buy."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(41))
        engine = _engine(store, clock)
        if variant == "exact":
            approval_id = _approve(store, clock, ids, f"approve {TICKET} {MINT} 0.2 100")
            decision = engine.check(_buy(clock, ids, approval_id), seat="bot-04-sniper")
            assert decision.passed is True
            assert decision.approval_id == approval_id
            return
        if variant == "wrong_size":
            approval_id = _approve(store, clock, ids, f"approve {TICKET} {MINT} 0.3 100")
            decision = engine.check(_buy(clock, ids, approval_id), seat="bot-04-sniper")
            assert decision.passed is False
            assert decision.reason == "approval_mismatch"
            return
        if variant == "wrong_mint":
            approval_id = _approve(store, clock, ids, f"approve {TICKET} {OTHER_MINT} 0.2 100")
            decision = engine.check(_buy(clock, ids, approval_id), seat="bot-04-sniper")
            assert decision.passed is False
            assert decision.reason == "approval_mismatch"
            return
        if variant == "missing_slippage":
            with pytest.raises(ValueError):
                _approve(store, clock, ids, f"approve {TICKET} {MINT} 0.2")
            decision = engine.check(_buy(clock, ids, f"apr-{ids.ulid()}"), seat="bot-04-sniper")
            assert decision.reason == "approval_missing"
            return
        if variant == "stale_ticket":
            approval_id = _approve(store, clock, ids, f"approve {STALE_TICKET} {MINT} 0.2 100")
            decision = engine.check(_buy(clock, ids, approval_id), seat="bot-04-sniper")
            assert decision.passed is False
            assert decision.reason == "approval_missing"
            return
        if variant == "bot_approver":
            with pytest.raises(ValidationError):
                _approve(store, clock, ids, f"approve {TICKET} {MINT} 0.2 100", by="bot-02-risk")
            decision = engine.check(_buy(clock, ids, f"apr-{ids.ulid()}"), seat="bot-04-sniper")
            assert decision.reason == "approval_missing"
            return
        if variant == "exit_without_exit_rule_approval":
            approval_id = _approve(store, clock, ids, f"approve {TICKET} {MINT} 0.2 100")
            decision = engine.check(
                _sell(clock, ids, approval_id), seat="bot-06-exit", exit_reason="exit_rule"
            )
            assert decision.passed is False
            assert decision.reason == "approval_mismatch"
            return
        raise AssertionError(f"unknown variant {variant}")
    finally:
        store.close()


def test_exit_rule_approval_authorises_manual_ticket_sell(tmp_path: Path) -> None:
    """INV-R-10: a manual-ticket exit-rule sell binds its exit_rule approval."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(41))
        engine = _engine(store, clock)
        approval_id = f"apr-{ids.ulid()}"
        record = ApprovalRecord(
            id=approval_id,
            kind="exit_rule",
            ticket_id=TICKET,
            mint=MINT,
            token_units=3_000_000,
            exit_rule_id="stop_loss",
            max_slippage_bps=100,
            approved_by="human:alice",
            raw_message="exit rule stop_loss",
            at=datetime.fromtimestamp(clock.now(), UTC),
        )
        record_human_approval(
            store, record, ts_utc=format_ts_utc(clock.now()), source="paper", correlation_id="test"
        )
        decision = engine.check(_sell(clock, ids, approval_id), seat="bot-06-exit", exit_reason="exit_rule")
        assert decision.passed is True
    finally:
        store.close()


def test_autonomous_paper_still_checks_limits(tmp_path: Path) -> None:
    """INV-R-11: autonomous-paper mints its own approval but every limit still trips."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(41))
        engine = _engine(store, clock, autonomy="autonomous-paper")
        tiny = engine.check(_buy(clock, ids, f"apr-{ids.ulid()}", size=5_000_000), seat="bot-04-sniper")
        assert tiny.passed is False
        assert tiny.reason == "size_too_small"
        assert tiny.approval is not None
        assert tiny.approval.approved_by == "risk_engine"
    finally:
        store.close()


def test_autonomy_level_switch_is_human_only_and_journaled(tmp_path: Path) -> None:
    """INV-R-11: level switches append ConfigChanged + JournalNote; reader defaults manual."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        assert read_autonomy(store) == "manual-ticket"
        ts = format_ts_utc(clock.now())
        rows = autonomy_rows("autonomous-paper", "human:alice", previous="manual-ticket", ts_utc=ts, source="paper", correlation_id="test")
        assert [row["type"] for row in rows] == ["ConfigChanged", "JournalNote"]
        assert rows[0]["payload"]["keys_changed"] == ["autonomy_level"]
        assert rows[1]["payload"]["note_kind"] == "note"
        store.append_batch(rows)
        assert read_autonomy(store) == "autonomous-paper"
    finally:
        store.close()


class _ScriptedCurves:
    def __init__(self, reads: list[CurveSnapshot]) -> None:
        self._reads = list(reads)

    async def curve(self, mint: str) -> CurveSnapshot | None:
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


async def test_consumed_approval_demands_fresh_approval(tmp_path: Path) -> None:
    """INV-R-10/12: an approval covers one order; reuse is approval_missing."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(41))
        engine = _engine(store, clock)
        snap = CurveSnapshot(mint=MINT, s_lamports=S0, t_units=T0)
        adapter = PaperAdapter(
            store=store, risk=engine, ids=ids, clock=clock, rng=make_rng(41),
            budget=RiskBudget(), price_source=_ScriptedCurves([snap, snap]), p_drop=0.0,
        )
        approval_id = _approve(store, clock, ids, f"approve {TICKET} {MINT} 0.2 100")

        async def drive(coro: Any) -> Any:
            task = asyncio.create_task(coro)
            for _ in range(400):
                if task.done():
                    break
                clock.advance_to(clock.now() + 1.0)
                await asyncio.sleep(0)
            return await task

        first = await drive(
            adapter.place(_buy(clock, ids, approval_id), seat="bot-04-sniper", correlation_id="test")
        )
        assert first.status.value == "filled"
        with pytest.raises(OrderRejectedError) as excinfo:
            await drive(
                adapter.place(_buy(clock, ids, approval_id), seat="bot-04-sniper", correlation_id="test")
            )
        assert excinfo.value.reason == "approval_missing"
    finally:
        store.close()
