<<<<<<< HEAD
"""SC 11: Intents reach exec.place only through the router (RT-02, D-06).

Below the autonomous-paper level the router journals refusals and approves
nothing — and this suite skips nothing.
=======
"""Criterion 11 (intent router): strategy Intents reach exec.place only through the router.

Below autonomous-paper the router journals a refusal and calls neither RiskEngine.check nor
exec.place, so nothing is approved. At autonomous-paper it allocates a ticket, obtains an
autonomous_paper approval from RiskEngine.check, and calls exec.place exactly once with the
ticket id and the approval id. Offline: the risk engine and exec.place are recording doubles.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

<<<<<<< HEAD
import ast
import asyncio
=======
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
from pathlib import Path
from typing import Any

from pumpgrok.core.adapter import OrderRequest
<<<<<<< HEAD
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.strategies.base import Intent
from pumpgrok.supervisor.intent_router import IntentRouter

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "pumpgrok"

MINT = "MintA11111111111111111111111111111111111"


def _open_store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(str(tmp_path / "ledger.sqlite"))


def _intent(**kwargs: Any) -> Intent:
    fields: dict[str, Any] = {
        "strategy_id": "momentum_breakout",
        "side": "buy",
        "mint": MINT,
        "size_lamports": 10_000,
        "reason": "test",
    }
    fields.update(kwargs)
    return Intent(**fields)


def _router(store: LedgerStore, placed: list[OrderRequest], **kwargs: Any) -> IntentRouter:
    async def _place(request: OrderRequest) -> None:
        placed.append(request)

    return IntentRouter(
        store=store,
        place=_place,
        clock=FixtureClock(0.0),
        **kwargs,
=======
from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.ids import IdFactory
from pumpgrok.ledger import ticket_refs
from pumpgrok.ledger.autonomy import autonomy_rows
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.engine.model import RiskDecision
from pumpgrok.strategies.base import Intent
from pumpgrok.supervisor.intent_router import IntentRouter

START = 1_700_000_000.0
MINT = "MintRouter1111111111111111111111111111111111"
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


def _intent(size: int = SIZE, decision: str = DECISION) -> Intent:
    return Intent(
        strategy_id=STRATEGY,
        mint=MINT,
        side="buy",
        size_lamports=size,
        decision_id=decision,
        reason="breakout",
        version_id="v" * 64,
    )


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "router.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", "1000000")
    store.set_meta("source", "paper")
    return store


def _set_autonomy(store: LedgerStore, policy: str) -> None:
    rows = autonomy_rows(
        policy,
        "human:owner",
        previous="manual-ticket",
        ts_utc=format_ts_utc(START),
        source="paper",
        correlation_id=CORR,
    )
    store.append_batch(rows)


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
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
    )


def _journal_notes(store: LedgerStore) -> list[dict[str, Any]]:
<<<<<<< HEAD
    return store.read(types=["JournalNote"], limit=None)


def test_below_autonomy_journals_refusal_and_places_nothing(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        placed: list[OrderRequest] = []
        router = _router(store, placed, autonomy="manual-ticket")
        result = asyncio.run(router.route(_intent()))
        assert result.status == "refused"
        assert result.ticket_id is None
        assert result.approval_id is None
        assert placed == []
        notes = _journal_notes(store)
        assert len(notes) == 1
        payload = notes[0]["payload"]
        assert "intent refused" in payload["text"]
        assert "momentum_breakout" in payload["text"]
        assert payload["refs"] == []
=======
    return [e["payload"] for e in store.read(types=["JournalNote"], limit=None)]


async def test_below_autonomous_paper_journals_refusal_and_approves_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        risk = FakeRisk()
        place = FakePlace()
        result = await _router(store, risk, place).route(_intent())

        assert result.status == "refused"
        assert result.reason == "autonomy_manual_ticket"
        assert place.calls == []
        assert risk.calls == []
        notes = _journal_notes(store)
        assert len(notes) == 1
        assert notes[0]["note_kind"] == "note"
        assert "refused" in notes[0]["text"]
        assert store.read(types=["ApprovalRecorded"], limit=None) == []
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
    finally:
        store.close()


<<<<<<< HEAD
def test_default_level_is_manual_and_refuses(tmp_path: Path) -> None:
    """With no level injected the ledger default (manual-ticket) refuses."""
    store = _open_store(tmp_path)
    try:
        placed: list[OrderRequest] = []
        router = _router(store, placed)
        result = asyncio.run(router.route(_intent()))
        assert result.status == "refused"
        assert placed == []
        assert len(_journal_notes(store)) == 1
    finally:
        store.close()


def test_at_autonomy_places_via_router_only(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        placed: list[OrderRequest] = []
        router = _router(store, placed, autonomy="autonomous-paper")
        result = asyncio.run(router.route(_intent(side="sell")))
        assert result.status == "placed"
        assert result.ticket_id is not None
        assert result.approval_id is not None
        assert len(placed) == 1
        request = placed[0]
        assert request.ticket_id == result.ticket_id
        assert request.approval_id == result.approval_id
        assert request.side.value == "sell"
        assert request.mint == MINT
        assert request.size_lamports == 10_000
    finally:
        store.close()


def test_unknown_strategy_id_refused_and_journaled(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        placed: list[OrderRequest] = []
        router = _router(store, placed, autonomy="autonomous-paper")
        # Intent validates its own ids, so forge one past construction.
        intent = _intent()
        object.__setattr__(intent, "strategy_id", "no_such_strategy")
        result = asyncio.run(router.route(intent))
        assert result.status == "refused"
        assert "unknown strategy" in result.reason
        assert placed == []
        assert len(_journal_notes(store)) == 1
    finally:
        store.close()


def test_sell_intent_allowed_at_autonomy(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        placed: list[OrderRequest] = []
        router = _router(store, placed, autonomy="autonomous-paper")
        result = asyncio.run(router.route(_intent(side="sell")))
        assert result.status == "placed"
        assert placed[0].side.value == "sell"
    finally:
        store.close()


def test_no_strategy_module_calls_place_directly() -> None:
    """T-15-15: no strategy module reaches exec.place outside the router.

    Static AST proof: nothing under ``strategies/`` names a ``place``
    attribute or imports the router's injected-call machinery.
    """
    offenders: list[str] = []
    for path in sorted((SRC / "strategies").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "place":
                offenders.append(f"{path.name}:{node.lineno}: .place")
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and ("intent_router" in node.module or "execution" in node.module)
            ):
                offenders.append(f"{path.name}:{node.lineno}: {node.module}")
    assert offenders == []
=======
async def test_at_autonomous_paper_allocates_checks_links_and_places_once(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        _set_autonomy(store, "autonomous-paper")
        risk = FakeRisk()
        place = FakePlace()
        result = await _router(store, risk, place).route(_intent())

        assert result.status == "submitted"
        assert result.ticket_id is not None
        assert result.ticket_id.startswith("SOL-20231114-")
        assert len(risk.calls) == 1
        assert risk.calls[0].ticket_id == result.ticket_id
        assert len(place.calls) == 1
        call = place.calls[0]
        assert call["ticket_id"] == result.ticket_id
        assert call["approval_id"] == "apr-01ARZ3NDEKTSV4RRFFQ69G5FAV"
        assert call["decision_id"] == DECISION
        assert ticket_refs.load_refs(store) == {result.ticket_id: STRATEGY}
    finally:
        store.close()
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
