"""SC 11: Intents reach exec.place only through the router (RT-02, D-06).

Below the autonomous-paper level the router journals refusals and approves
nothing -- and this suite skips nothing.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any

from pumpgrok.core.adapter import OrderRequest
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
    )


def _journal_notes(store: LedgerStore) -> list[dict[str, Any]]:
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
    finally:
        store.close()


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
