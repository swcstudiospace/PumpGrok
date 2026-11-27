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
    finally:
        store.close()


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
    finally:
        store.close()
