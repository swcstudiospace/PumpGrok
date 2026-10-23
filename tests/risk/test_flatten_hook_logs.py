"""The kill-poll flatten hook logs every position it leaves open at ERROR (G7).

The hook runs from ``RiskEngine.poll_kill_sources`` on the gateway and on the supervisor. A
position with no ledger mark and no price source cannot be valued, so the flatten leaves it open.
That must be visible in the logs, with the mint and the detail, and the hook must not report the
flatten as complete. No network, no price source.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.paper_adapter import PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.killswitch import InflightBarrier, killswitch_file
from pumpgrok.tools.risk.kill_switch import flatten_hook_for

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
MINT = "So11111111111111111111111111111111111111112"
TICKET = "SOL-20260201-001"
LOGGER = "pumpgrok.tools.risk.kill_switch"


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", "10000000000")
    store.set_meta("source", "paper")
    return store


def _open_position(store: LedgerStore, clock: FixtureClock) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key="pos-no-mark",
        type="PositionOpened",
        payload={
            "source": "paper",
            "mint": MINT,
            "price_entry": "0.00001",
            "token_units": 3_000_000,
            "cost_basis_lamports": 200_000_000,
            "opened_ts_utc": format_ts_utc(clock.now()),
            "symbol": "TST",
            "creator": "Creator1111111111111111111111111111111111",
            "ticket_id": TICKET,
            "score": "0.8",
        },
    )


def _run_flatten(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _open_position(store, clock)
        latch = killswitch_file(tmp_path / "desk")
        latch.parent.mkdir(parents=True)
        latch.write_text("FLATTEN close all", encoding="utf-8")
        ids = IdFactory(clock, random.Random(7))
        engine = RiskEngine(
            store=store,
            budget=RiskBudget(),
            ids=ids,
            clock=clock,
            autonomy="autonomous-paper",
            killswitch_path=latch,
            env={},
        )
        # No price source: the adapter has no curve and no ledger mark to value the sell with.
        adapter = PaperAdapter(
            store=store,
            risk=engine,
            ids=ids,
            clock=clock,
            rng=make_rng(7),
            budget=RiskBudget(),
            price_source=None,
            p_drop=0.0,
        )
        engine.attach_flatten_hook(
            flatten_hook_for(store, adapter.inflight_barrier, adapter.close_position)
        )
        asyncio.run(engine.poll_kill_sources())
        # The position is still open: the flatten did not close it.
        assert store.read(types=["PositionClosed"], limit=None) == []
    finally:
        store.close()


def test_unflattened_position_is_logged_at_error_with_mint_and_detail(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    _run_flatten(tmp_path)
    errors = [r for r in caplog.records if r.name == LOGGER and r.levelno == logging.ERROR]
    assert len(errors) == 1, [(r.levelname, r.getMessage()) for r in caplog.records]
    message = errors[0].getMessage()
    assert MINT in message, message
    assert "no_mark" in message, message


def test_position_closed_by_another_caller_is_not_logged_at_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """PR 11 finding 1: the poll hook must not log ERROR for a position another caller closed."""
    caplog.set_level(logging.INFO, logger=LOGGER)
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _open_position(store, clock)

        async def overlapping_close(*, mint: str, ticket_id: str, reason: str) -> dict[str, Any]:
            store.append(
                ts_utc=format_ts_utc(clock.now()),
                source="paper",
                correlation_id="other-caller",
                idempotency_key="closed-by-other",
                type="PositionClosed",
                payload={
                    "source": "paper",
                    "mint": mint,
                    "price_exit": "0.00001",
                    "proceeds_lamports": 0,
                    "realized_pnl_lamports": 0,
                    "reason": reason,
                    "pnl_pct": "0",
                    "hold_seconds": 0,
                    "venue_tx_ref": "",
                },
            )
            return {"status": "no_position", "mint": mint}

        hook = flatten_hook_for(store, InflightBarrier(), overlapping_close)
        asyncio.run(hook())
    finally:
        store.close()
    errors = [r for r in caplog.records if r.name == LOGGER and r.levelno == logging.ERROR]
    assert errors == [], [r.getMessage() for r in errors]
