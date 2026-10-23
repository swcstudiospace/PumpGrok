"""RISK-004 / review finding 18: a flatten request closes every open position.

The operator's ``flatten_request`` waits for the in-flight barrier, then closes
each open position with reason ``kill_flatten`` through the paper adapter's
``close_position``. A barrier that never clears closes nothing.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.killswitch import InflightBarrier
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.tools.risk.kill_switch import (
    FLATTEN_BARRIER_TIMEOUT_S,
    FLATTEN_CLOSE_BUDGET_S,
    KILL_SWITCH_SPEC,
    KillSwitchIn,
    build_kill_switch_tool,
    run_kill_switch,
)

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT_A = "So11111111111111111111111111111111111111112"
MINT_B = "So22222222222222222222222222222222222222222"
S0 = 42_000_000_000
T0 = 764_000_000_000_000


@pytest.fixture(autouse=True)
def _no_env_killswitch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PUMPGROK_KILLSWITCH", raising=False)


class _ScriptedCurves:
    """Serve the same live curve for every mint read."""

    async def curve(self, mint: str) -> CurveSnapshot | None:
        return CurveSnapshot(mint=mint, s_lamports=S0, t_units=T0)


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _open(store: LedgerStore, clock: FixtureClock, mint: str, units: int) -> None:
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
            "cost_basis_lamports": 1_000_000,
            "opened_ts_utc": format_ts_utc(START),
            "symbol": "TST",
            "creator": "Creator1111111111111111111111111111111111",
            "ticket_id": TICKET,
            "score": "0.8",
        },
    )


def _adapter(store: LedgerStore, clock: FixtureClock) -> PaperAdapter:
    ids = IdFactory(clock, random.Random(7))
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=ids,
        clock=clock,
        autonomy="autonomous-paper",
        get_reserves=lambda _mint: (S0, T0),
        env={},
    )
    return PaperAdapter(
        store=store,
        risk=engine,
        ids=ids,
        clock=clock,
        rng=make_rng(7),
        budget=RiskBudget(),
        price_source=_ScriptedCurves(),
        p_drop=0.0,
    )


def _closed_rows(store: LedgerStore) -> list[dict[str, Any]]:
    return store.read(types=["PositionClosed"], limit=None)


async def test_flatten_request_closes_the_open_position(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _open(store, clock, MINT_A, 100)
    adapter = _adapter(store, clock)
    tool = build_kill_switch_tool(
        store,
        clock,
        tmp_path / "KILLSWITCH",
        close_position=adapter.close_position,
        barrier=InflightBarrier(),
    )

    out = await tool(KillSwitchIn(action="flatten_request", reason="close everything"))

    closed = _closed_rows(store)
    store.close()
    assert out.flatten_status == "completed"
    assert [(o.mint, o.status) for o in out.flatten_outcomes] == [(MINT_A, "closed")]
    assert len(closed) == 1
    assert closed[0]["payload"]["mint"] == MINT_A
    assert closed[0]["payload"]["reason"] == "kill_flatten"


async def test_flatten_request_with_no_positions_closes_nothing(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    adapter = _adapter(store, clock)
    tool = build_kill_switch_tool(
        store,
        clock,
        tmp_path / "KILLSWITCH",
        close_position=adapter.close_position,
        barrier=InflightBarrier(),
    )

    out = await tool(KillSwitchIn(action="flatten_request", reason="nothing open"))

    closed = _closed_rows(store)
    store.close()
    assert out.flatten_status == "completed"
    assert out.flatten_outcomes == []
    assert closed == []


async def test_barrier_that_never_clears_closes_nothing(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _open(store, clock, MINT_A, 100)
    _open(store, clock, MINT_B, 50)
    calls: list[str] = []

    async def recording_close(*, mint: str, ticket_id: str, reason: str) -> dict[str, Any]:
        calls.append(mint)
        return {"status": "closed", "mint": mint}

    stuck = InflightBarrier()
    stuck.register("order-that-never-settles")

    out = await run_kill_switch(
        KillSwitchIn(action="flatten_request", reason="barrier test"),
        store,
        clock,
        tmp_path / "KILLSWITCH",
        close_position=recording_close,
        barrier=stuck,
        barrier_timeout_s=0.05,
    )

    closed = _closed_rows(store)
    store.close()
    assert out["flatten_status"] == "blocked"
    assert out["flatten_outcomes"] == []
    assert calls == []
    assert closed == []


async def test_flatten_without_a_wired_closer_reports_unavailable(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _open(store, clock, MINT_A, 100)
    tool = build_kill_switch_tool(store, clock, tmp_path / "KILLSWITCH")

    out = await tool(KillSwitchIn(action="flatten_request", reason="no closer"))

    closed = _closed_rows(store)
    store.close()
    assert out.flatten_status == "unavailable"
    assert closed == []


async def test_not_closed_adapter_status_is_reported_not_flattened(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _open(store, clock, MINT_A, 100)

    async def no_mark_close(*, mint: str, ticket_id: str, reason: str) -> dict[str, Any]:
        return {"status": "no_mark", "mint": mint}

    out = await run_kill_switch(
        KillSwitchIn(action="flatten_request", reason="no mark"),
        store,
        clock,
        tmp_path / "KILLSWITCH",
        close_position=no_mark_close,
        barrier=InflightBarrier(),
    )
    store.close()
    assert out["flatten_status"] == "incomplete"
    assert out["flatten_outcomes"] == [
        {"mint": MINT_A, "ticket_id": TICKET, "status": "not_flattened", "detail": "status=no_mark"}
    ]


def test_closer_without_in_flight_barrier_is_refused_at_wiring(tmp_path: Path) -> None:
    """A closer with no barrier would flatten without waiting for live orders: refuse it."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)

    async def closer(*, mint: str, ticket_id: str, reason: str) -> dict[str, Any]:
        return {"status": "closed", "mint": mint}

    with pytest.raises(ValueError, match="in-flight barrier"):
        build_kill_switch_tool(store, clock, tmp_path / "KILLSWITCH", close_position=closer)
    store.close()


def test_flatten_deadlines_cover_the_adapter_confirmation_bound() -> None:
    """Review finding 3: the registry deadline must outlast the barrier wait and closes.

    The registry cancels a tool call at ``spec.timeout_s``. An order may legitimately
    stay in flight for the adapter's ``confirm_timeout_s``, so the flatten barrier
    bound must cover that bound, and the tool deadline must cover the barrier wait
    plus the closing work. Otherwise flatten is cancelled mid-close.
    """
    confirm_bound = EngineLimits().confirm_timeout_s
    assert confirm_bound <= FLATTEN_BARRIER_TIMEOUT_S
    assert KILL_SWITCH_SPEC.timeout_s >= FLATTEN_BARRIER_TIMEOUT_S + FLATTEN_CLOSE_BUDGET_S
    assert KILL_SWITCH_SPEC.timeout_s <= 300.0


def _close_by_other_caller(store: LedgerStore, clock: FixtureClock, mint: str) -> None:
    """The overlapping caller's close: a PositionClosed row, as the paper adapter writes it."""
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="other-caller",
        idempotency_key=f"closed-by-other-{mint[-4:]}",
        type="PositionClosed",
        payload={
            "source": "paper",
            "mint": mint,
            "price_exit": "0.00001",
            "proceeds_lamports": 0,
            "realized_pnl_lamports": 0,
            "reason": "kill_flatten",
            "pnl_pct": "0",
            "hold_seconds": 0,
            "venue_tx_ref": "",
        },
    )


async def test_position_closed_by_another_caller_is_not_reported_unflattened(
    tmp_path: Path,
) -> None:
    """PR 11 finding 1: a no_position close whose mint is no longer open counts as flat."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _open(store, clock, MINT_A, 100)

    async def overlapping_close(*, mint: str, ticket_id: str, reason: str) -> dict[str, Any]:
        _close_by_other_caller(store, clock, mint)
        return {"status": "no_position", "mint": mint}

    out = await run_kill_switch(
        KillSwitchIn(action="flatten_request", reason="overlap"),
        store,
        clock,
        tmp_path / "KILLSWITCH",
        close_position=overlapping_close,
        barrier=InflightBarrier(),
    )
    store.close()
    assert out["flatten_status"] == "completed", out
    assert [(o["mint"], o["status"]) for o in out["flatten_outcomes"]] == [(MINT_A, "closed")]


async def test_no_position_while_mint_is_still_open_stays_incomplete(tmp_path: Path) -> None:
    """Guard: a no_position close does not count as flat while the ledger still lists the mint."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _open(store, clock, MINT_A, 100)

    async def refusing_close(*, mint: str, ticket_id: str, reason: str) -> dict[str, Any]:
        return {"status": "no_position", "mint": mint}

    out = await run_kill_switch(
        KillSwitchIn(action="flatten_request", reason="still open"),
        store,
        clock,
        tmp_path / "KILLSWITCH",
        close_position=refusing_close,
        barrier=InflightBarrier(),
    )
    store.close()
    assert out["flatten_status"] == "incomplete", out
    assert [(o["mint"], o["status"]) for o in out["flatten_outcomes"]] == [
        (MINT_A, "not_flattened")
    ]
