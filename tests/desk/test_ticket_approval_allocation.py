<<<<<<< HEAD
"""SC 11: ticket and approval allocation correctness through the router."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.strategy_state import read_attribution_refs
from pumpgrok.ledger.tickets import TICKET_RE, day_ticket_count
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.strategies.base import Intent
from pumpgrok.supervisor.intent_router import IntentRouter

MINT = "MintA11111111111111111111111111111111111"
APR_RE = re.compile(r"^apr-[0-9A-HJKMNP-TV-Z]{26}$")


def _open_store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(str(tmp_path / "ledger.sqlite"))


def _router(store: LedgerStore, placed: list[OrderRequest]) -> IntentRouter:
    async def _place(request: OrderRequest) -> None:
        placed.append(request)

    return IntentRouter(
        store=store,
        place=_place,
        clock=FixtureClock(1_700_000_000.0),
        autonomy="autonomous-paper",
    )


def _intent(strategy_id: str = "momentum_breakout") -> Intent:
    return Intent(
        strategy_id=strategy_id,
        side="buy",
        mint=MINT,
        size_lamports=10_000,
        reason="alloc",
    )


def test_ticket_and_approval_allocated_then_placed(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        placed: list[OrderRequest] = []
        router = _router(store, placed)
        result = asyncio.run(router.route(_intent()))
        assert result.status == "placed"
        assert result.ticket_id is not None and TICKET_RE.fullmatch(result.ticket_id)
        assert result.ticket_id == "SOL-20231114-001"
        assert result.approval_id is not None and APR_RE.fullmatch(result.approval_id)
        assert placed[0].ticket_id == result.ticket_id
        assert placed[0].approval_id == result.approval_id
        # The ticket row and the attribution ref row both carry the ticket id.
        assert day_ticket_count(store, "20231114") == 2
        assert read_attribution_refs(store, "momentum_breakout") == [
            {"ticket_id": "SOL-20231114-001", "mint": MINT}
        ]
    finally:
        store.close()


def test_tickets_allocate_sequentially(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        placed: list[OrderRequest] = []
        router = _router(store, placed)
        first = asyncio.run(router.route(_intent()))
        second = asyncio.run(router.route(_intent()))
        assert (first.ticket_id, second.ticket_id) == (
            "SOL-20231114-001",
            "SOL-20231114-002",
        )
        assert first.approval_id != second.approval_id
        assert len(placed) == 2
=======
"""Criterion 11 (ticket and approval allocation): idempotency, slice, binding, failure paths.

An Intent submitted twice with one decision_id gets one ticket and one exec.place call. A
size over the strategy slice, an unknown strategy, a risk refusal, and an approval that does
not bind this ticket are each journaled with zero exec.place calls. A ticket allocation
failure is journaled, not raised past the router. Offline: the risk engine and exec.place are
recording doubles.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.ids import IdFactory
from pumpgrok.ledger import ticket_refs
from pumpgrok.ledger.autonomy import autonomy_rows
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.ledger.tickets import TicketAllocationFailed
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.engine.model import RiskDecision
from pumpgrok.strategies.base import Intent
from pumpgrok.supervisor import intent_router
from pumpgrok.supervisor.intent_router import IntentRouter

START = 1_700_000_000.0
MINT = "MintAlloc11111111111111111111111111111111111"
STRATEGY = "momentum_breakout"
DECISION = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
CORR = "01ARZ3NDEKTSV4RRFFQ69G5FAW"
SLICE = 1_000_000
SIZE = 400_000


@dataclass
class FakeRisk:
    """RiskEngine.check double: approves with an autonomous_paper approval, or refuses."""

    passed: bool = True
    reason: str = "pass"
    approval_ticket: str | None = None
    calls: list[OrderRequest] = field(default_factory=list)

    def check(self, order: OrderRequest, **_: Any) -> RiskDecision:
        self.calls.append(order)
        if not self.passed:
            return RiskDecision(
                passed=False, reason=self.reason, order_hash="0" * 64, decision_id=order.decision_id
            )
        approval = ApprovalRecord(
            id="apr-01ARZ3NDEKTSV4RRFFQ69G5FAV",
            kind="autonomous_paper",
            ticket_id=self.approval_ticket or order.ticket_id,
            mint=order.mint,
            size_lamports=order.size_lamports,
            max_slippage_bps=order.max_slippage_bps,
            approved_by="risk_engine",
            raw_message=f"autonomous-paper {order.side.value} {order.ticket_id}",
            at=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        )
        return RiskDecision(
            passed=True,
            reason="pass",
            order_hash="0" * 64,
            decision_id=order.decision_id,
            approval_id=approval.id,
            approval=approval,
            size_lamports=order.size_lamports,
        )


@dataclass
class FakePlace:
    """exec.place double: records each call and answers as the adapter would."""

    calls: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(payload)
        return {"status": "filled", "ticket_id": payload["ticket_id"], "reason": ""}


def _intent(size: int = SIZE) -> Intent:
    return Intent(
        strategy_id=STRATEGY,
        mint=MINT,
        side="buy",
        size_lamports=size,
        decision_id=DECISION,
        reason="breakout",
        version_id="v" * 64,
    )


def _armed(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "alloc.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", "1000000")
    store.set_meta("source", "paper")
    store.append_batch(
        autonomy_rows(
            "autonomous-paper",
            "human:owner",
            previous="manual-ticket",
            ts_utc=format_ts_utc(START),
            source="paper",
            correlation_id=CORR,
        )
    )
    return store


def _router(
    store: LedgerStore,
    risk: FakeRisk,
    place: FakePlace,
    *,
    slices: dict[str, int] | None = None,
) -> IntentRouter:
    clock = FixtureClock(start=START)
    return IntentRouter(
        exec_place=place,
        risk=risk,
        store=store,
        clock=clock,
        ids=IdFactory(clock, random.Random(7)),
        slices={STRATEGY: SLICE} if slices is None else slices,
        max_slippage_bps=100,
    )


def _notes(store: LedgerStore) -> list[dict[str, Any]]:
    return [e["payload"] for e in store.read(types=["JournalNote"], limit=None)]


def _tickets(store: LedgerStore) -> list[dict[str, Any]]:
    return [p for p in _notes(store) if p["note_kind"] == "ticket"]


async def test_same_decision_submitted_twice_gives_one_ticket_and_one_place(
    tmp_path: Path,
) -> None:
    store = _armed(tmp_path)
    try:
        risk = FakeRisk()
        place = FakePlace()
        router = _router(store, risk, place)
        first = await router.route(_intent())
        second = await router.route(_intent())

        assert first.status == "submitted"
        assert second.status == "duplicate"
        assert second.ticket_id == first.ticket_id
        assert len(_tickets(store)) == 1
        assert len(place.calls) == 1
        assert len(risk.calls) == 1
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
    finally:
        store.close()


<<<<<<< HEAD
def test_legacy_strategy_writes_no_attribution_ref(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        placed: list[OrderRequest] = []
        router = _router(store, placed)
        result = asyncio.run(router.route(_intent("legacy_screening")))
        assert result.status == "placed"
        assert read_attribution_refs(store, "legacy_screening") == []
        assert day_ticket_count(store, "20231114") == 1
    finally:
        store.close()


def test_refusal_allocates_no_ticket_no_approval(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        placed: list[OrderRequest] = []

        async def _place(request: OrderRequest) -> None:
            placed.append(request)

        router = IntentRouter(
            store=store,
            place=_place,
            clock=FixtureClock(1_700_000_000.0),
            autonomy="manual-ticket",
        )
        result = asyncio.run(router.route(_intent()))
        assert result.status == "refused"
        assert result.ticket_id is None and result.approval_id is None
        assert day_ticket_count(store, "20231114") == 0
        assert placed == []
=======
async def test_size_over_strategy_slice_is_refused_and_journaled(tmp_path: Path) -> None:
    store = _armed(tmp_path)
    try:
        risk = FakeRisk()
        place = FakePlace()
        result = await _router(store, risk, place).route(_intent(size=SLICE + 1))
        assert result.status == "refused"
        assert result.reason == "slice_exceeded"
        assert risk.calls == []
        assert place.calls == []
        refusals = [p for p in _notes(store) if p["text"].startswith("refused ")]
        assert len(refusals) == 1
        assert refusals[0]["text"].endswith("slice_exceeded")
    finally:
        store.close()


async def test_unknown_strategy_is_refused_before_risk_or_place(tmp_path: Path) -> None:
    store = _armed(tmp_path)
    try:
        risk = FakeRisk()
        place = FakePlace()
        result = await _router(store, risk, place, slices={}).route(_intent())

        assert result.status == "refused"
        assert result.reason == "unknown_strategy"
        assert risk.calls == []
        assert place.calls == []
    finally:
        store.close()


async def test_risk_refusal_is_journaled_with_zero_place_calls(tmp_path: Path) -> None:
    store = _armed(tmp_path)
    try:
        risk = FakeRisk(passed=False, reason="max_open_positions")
        place = FakePlace()
        result = await _router(store, risk, place).route(_intent())

        assert result.status == "refused"
        assert result.reason == "max_open_positions"
        assert len(risk.calls) == 1
        assert place.calls == []
        assert store.read(types=["ApprovalRecorded"], limit=None) == []
    finally:
        store.close()


async def test_approval_for_another_ticket_is_refused_before_place(tmp_path: Path) -> None:
    store = _armed(tmp_path)
    try:
        risk = FakeRisk(approval_ticket="SOL-20991231-999")
        place = FakePlace()
        result = await _router(store, risk, place).route(_intent())

        assert result.status == "refused"
        assert result.reason == "approval_mismatch"
        assert place.calls == []
    finally:
        store.close()


async def test_ticket_allocation_failure_is_journaled_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _armed(tmp_path)
    try:

        def _fail(*_: object, **__: object) -> str:
            raise TicketAllocationFailed("could not allocate a ticket for 20231114")

        monkeypatch.setattr(intent_router, "allocate_ticket", _fail)
        risk = FakeRisk()
        place = FakePlace()
        result = await _router(store, risk, place).route(_intent())

        assert result.status == "refused"
        assert result.reason == "ticket_allocation_failed"
        assert risk.calls == []
        assert place.calls == []
        refusals = [p for p in _notes(store) if p["text"].startswith("refused ")]
        assert len(refusals) == 1
    finally:
        store.close()


async def test_routed_decision_is_linked_to_its_strategy(tmp_path: Path) -> None:
    store = _armed(tmp_path)
    try:
        place = FakePlace()
        result = await _router(store, FakeRisk(), place).route(_intent())

        assert result.ticket_id is not None
        assert ticket_refs.load_refs(store) == {result.ticket_id: STRATEGY}
        assert place.calls[0]["size_lamports"] == SIZE
        assert place.calls[0]["decision_id"] == DECISION
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
    finally:
        store.close()
