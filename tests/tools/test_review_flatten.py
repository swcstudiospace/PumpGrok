"""Review finding 18: a flatten request must produce a sell intent per open position.

A ``flatten_request`` acknowledges the operator's request only if it names
every position that must close. Closed and zero-unit positions produce no
intent, and a plain ``set`` produces none.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.tools.risk.kill_switch import KillSwitchIn, build_kill_switch_tool

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
TICKET = "SOL-20260201-001"
MINT_A = "So11111111111111111111111111111111111111112"
MINT_B = "So22222222222222222222222222222222222222222"
MINT_C = "So33333333333333333333333333333333333333333"
MINT_ZERO = "So44444444444444444444444444444444444444444"


@pytest.fixture(autouse=True)
def _no_env_killswitch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PUMPGROK_KILLSWITCH", raising=False)


def _store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(str(tmp_path / "ledger.sqlite"))


def _append(store: LedgerStore, clock: FixtureClock, type: str, payload: dict[str, Any]) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"seed-{store.count() + 1}",
        type=type,
        payload=payload,
    )


def _open(store: LedgerStore, clock: FixtureClock, mint: str, units: int) -> None:
    _append(
        store,
        clock,
        "PositionOpened",
        {
            "source": "paper",
            "mint": mint,
            "price_entry": "0.00001",
            "token_units": units,
            "cost_basis_lamports": 1_000,
            "opened_ts_utc": format_ts_utc(START),
            "symbol": "TST",
            "creator": "Creator1111111111111111111111111111111111",
            "ticket_id": TICKET,
            "score": "0.8",
        },
    )


async def test_flatten_request_emits_sell_intent_for_every_open_position(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _open(store, clock, MINT_A, 100)
    _open(store, clock, MINT_B, 250)
    _open(store, clock, MINT_C, 40)
    _append(
        store,
        clock,
        "PositionClosed",
        {
            "source": "paper",
            "mint": MINT_C,
            "price_exit": "0.00002",
            "proceeds_lamports": 2_000,
            "realized_pnl_lamports": 1_000,
            "reason": "manual",
        },
    )
    _open(store, clock, MINT_ZERO, 0)
    tool = build_kill_switch_tool(store, clock)

    out = await tool(KillSwitchIn(action="flatten_request", reason="close everything"))
    store.close()

    assert out.flatten_requested is True
    intents = {intent.mint: intent for intent in out.flatten_intents}
    assert set(intents) == {MINT_A, MINT_B}
    assert intents[MINT_A].token_units == 100
    assert intents[MINT_B].token_units == 250
    for intent in out.flatten_intents:
        assert intent.side == "sell"
        assert intent.ticket_id == TICKET
        assert intent.exit_reason == "kill_flatten"


async def test_flatten_request_with_no_positions_emits_no_intents(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    tool = build_kill_switch_tool(store, clock)

    out = await tool(KillSwitchIn(action="flatten_request", reason="nothing open"))
    store.close()

    assert out.flatten_requested is True
    assert out.flatten_intents == []


async def test_plain_set_emits_no_flatten_intents(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _open(store, clock, MINT_A, 100)
    tool = build_kill_switch_tool(store, clock)

    out = await tool(KillSwitchIn(action="set", reason="halt only"))
    store.close()

    assert out.flatten_requested is False
    assert out.flatten_intents == []
