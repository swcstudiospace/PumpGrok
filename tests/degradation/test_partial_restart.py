"""INV-R-35: killing and restarting one seat leaves shared state consistent.

A crashing seat exhausts its restart budget and latches observe-only while
its peers keep ticking; the ledger verifies, idempotency keys stay unique,
and a tripped breaker reconstructed from the ledger keeps its cooldown.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pumpgrok.core.idempotency import exec_place_key
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.breakers import BreakerSet
from pumpgrok.supervisor.scheduler import ROSTER, Supervisor
from pumpgrok.supervisor.seat_task import ObserveOnly, SeatContext, SeatTask

BASE = 1767225600.0


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))


def _ctx(store: LedgerStore, clock: FixtureClock, seat: str) -> SeatContext:
    return SeatContext(
        seat_id=seat,
        clock=clock,
        rng=make_rng(11),
        store=store,
        source="replay",
        correlation_id="desk",
    )


async def _boom(ctx: SeatContext) -> dict[str, Any]:
    raise RuntimeError("seat crashed")


async def _ok(ctx: SeatContext) -> dict[str, Any]:
    return {"ok": True}


async def test_single_seat_restart_latches_observe_only_while_others_tick(
    tmp_path: Path,
) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        observe_only = ObserveOnly()
        crashing = SeatTask(
            "bot-01-scout",
            10.0,
            _boom,
            clock=clock,
            rng=make_rng(11),
            store=store,
            observe_only=observe_only,
        )
        healthy = SeatTask(
            "bot-07-shill",
            300.0,
            _ok,
            clock=clock,
            rng=make_rng(11),
            store=store,
            observe_only=observe_only,
        )
        for _ in range(6):
            assert await crashing.run_guarded(_ctx(store, clock, "bot-01-scout")) == "crash"
            assert await healthy.run_guarded(_ctx(store, clock, "bot-07-shill")) == "ok"
            clock.advance_to(clock.now() + 60.0)
        assert observe_only.is_latched("bot-01-scout")
        assert not observe_only.is_latched("bot-07-shill")
        assert healthy.cycles == 6
        escalations = [
            event for event in store.read(limit=None) if event["type"] == "Escalation"
        ]
        kinds = [event["payload"]["kind"] for event in escalations]
        assert kinds.count("bot_restart_exhausted") == 1
        keys = [event["idempotency_key"] for event in store.read(limit=None)]
        assert len(set(keys)) == len(keys)
        assert store.verify() is True
    finally:
        store.close()


def _rejected_row(offset_s: float, index: int) -> dict:
    return {
        "ts_utc": format_ts_utc(BASE + offset_s),
        "source": "paper",
        "correlation_id": "desk",
        "idempotency_key": f"rejected-{index}",
        "type": "OrderRejected",
        "payload": {
            "source": "paper",
            "order_id": f"order-{index}",
            "decision_id": f"decision-{index}",
            "reason": "rpc_error",
            "detail": "rpc failed",
            "stage": "ACCEPTED",
        },
    }


def test_tripped_breaker_survives_restart_with_cooldown(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        store.append_batch([_rejected_row(offset, index) for index, offset in enumerate((0.0, 1.0, 2.0))])
        first = BreakerSet(store, clock)
        first.refresh(
            ts_utc=format_ts_utc(BASE + 2.0),
            source="paper",
            correlation_id="desk",
            equity_now=1_000_000_000,
        )
        assert "exec_errors" in first.open_breakers()
        remaining_before = first.exec_errors.remaining_cooldown()
        assert remaining_before > 0
        restarted = BreakerSet(store, clock)
        restarted.sync_from_ledger()
        assert "exec_errors" in restarted.open_breakers()
        assert restarted.exec_errors.opened_at == first.exec_errors.opened_at
        assert restarted.exec_errors.remaining_cooldown() == remaining_before
        assert store.verify() is True
    finally:
        store.close()


async def test_restarted_supervisor_resumes_from_ledger_state(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        first = Supervisor(
            store=store, clock=clock, rng=make_rng(11), cycles=dict.fromkeys(ROSTER, _ok)
        )
        outcomes = await first.run_once()
        assert all(outcome == "ok" for outcome in outcomes.values())
        clock.advance_to(BASE + 60.0)
        restarted = Supervisor(
            store=store, clock=clock, rng=make_rng(11), cycles=dict.fromkeys(ROSTER, _ok)
        )
        outcomes = await restarted.run_once()
        assert all(outcome == "ok" for outcome in outcomes.values())
        assert restarted.ready() is True
        rollovers = [
            row for row in store.read(limit=None) if row["type"] == "DailyRollover"
        ]
        assert len(rollovers) == 1
        keys = [event["idempotency_key"] for event in store.read(limit=None)]
        assert len(set(keys)) == len(keys)
        assert store.verify() is True
    finally:
        store.close()
