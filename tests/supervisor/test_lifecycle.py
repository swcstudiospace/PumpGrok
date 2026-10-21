"""Graceful shutdown, signals, readyz, and observe-only resolution.

SIGTERM/SIGINT stops scheduling and drains cycles within 30 s, a ledger
snapshot is written, the JSONL export flushes, var/health.json records
``status=stopped``, and the process exits 0. A second signal never forces.
``GET /readyz`` returns 200 only after the ledger reconciles CONSISTENT
and every seat completes one cycle. RISK-006: seats in observe-only cannot
resolve paper-write tools; sniper or risk observe-only puts the desk
observe-only for buys while exits continue.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.supervisor.health import HealthServer
from pumpgrok.supervisor.lifecycle import (
    cancel_and_wait,
    drain,
    install_signal_handlers,
    shutdown,
)
from pumpgrok.supervisor.scheduler import ROSTER, Supervisor
from pumpgrok.supervisor.seat_task import SeatContext


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))


async def _ok(ctx: SeatContext) -> dict[str, Any]:
    return {"ok": True}


def _supervisor(store: LedgerStore, clock: FixtureClock) -> Supervisor:
    return Supervisor(store=store, clock=clock, rng=make_rng(13), cycles=dict.fromkeys(ROSTER, _ok))


async def test_request_stop_is_idempotent_second_signal_never_forces(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    try:
        supervisor = _supervisor(store, clock)
        assert supervisor.stopped is False
        supervisor.request_stop("SIGTERM")
        assert supervisor.stopped is True
        supervisor.request_stop("SIGTERM")
        assert supervisor.stopped is True
    finally:
        store.close()


async def test_drain_returns_finished_when_tasks_complete_in_grace() -> None:
    clock = FixtureClock(start=0.0)

    async def _quick() -> str:
        return "done"

    first = asyncio.ensure_future(_quick())
    done, cancelled = await drain({first}, 30.0, clock)
    assert (done, cancelled) == (1, 0)


async def test_drain_cancels_stragglers_after_grace() -> None:
    clock = FixtureClock(start=0.0)

    async def _slow() -> str:
        await clock.sleep(1_000.0)
        return "slow"

    slow = asyncio.ensure_future(_slow())
    await asyncio.sleep(0)

    async def _advance() -> None:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        clock.advance_to(30.0)

    (done, cancelled), _ = await asyncio.gather(drain({slow}, 30.0, clock), _advance())
    assert done == 0
    assert cancelled == 1
    assert slow.done()


async def test_cancel_and_wait_swallows_cancelled() -> None:
    async def _wait() -> None:
        await asyncio.sleep(3600.0)

    task = asyncio.ensure_future(_wait())
    await asyncio.sleep(0)
    await cancel_and_wait(task)
    assert task.done()
    await cancel_and_wait(None)


async def test_shutdown_snapshots_exports_health_and_exits_0(tmp_path: Path) -> None:
    clock = FixtureClock(start=5_000.0)
    store = _store(tmp_path)
    try:
        supervisor = _supervisor(store, clock)
        await supervisor.run_once()
        assert supervisor.ready() is True
        health_path = tmp_path / "health.json"
        code = await shutdown(
            supervisor,
            store=store,
            health_path=str(health_path),
            journal_dir=str(tmp_path / "journal"),
            trades_path=str(tmp_path / "trades.jsonl"),
        )
        assert code == 0
        assert supervisor.stopped is True
        body = json.loads(health_path.read_text(encoding="utf-8"))
        assert body["status"] == "stopped"
        snapshots = store.read_snapshots()
        assert len(snapshots) == 1
        assert int(snapshots[0]["seq"]) == store.count()
    finally:
        store.close()


async def test_readyz_requires_consistent_ledger_and_one_cycle_each(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    try:
        supervisor = _supervisor(store, clock)
        assert supervisor.ready() is False
        await supervisor.run_once()
        assert supervisor.ready() is True
    finally:
        store.close()


def _get(port: int, path: str) -> tuple[int, dict[str, Any]]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8"))


async def test_health_server_healthz_and_readyz_contracts(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    try:
        supervisor = _supervisor(store, clock)
        server = HealthServer(clock, supervisor.health_status, lambda: False)
        port = await server.start("127.0.0.1", 0)
        try:
            code, _ = await asyncio.to_thread(_get, port, "/readyz")
            assert code == 503
            await supervisor.run_once()
            code, body = await asyncio.to_thread(_get, port, "/healthz")
            assert code == 200
            assert body["status"] == "ok"
            assert set(body["seats"]) == set(ROSTER)
            assert body["ledger_status"] == "CONSISTENT"
            ready_server = HealthServer(clock, supervisor.health_status, supervisor.ready)
            ready_port = await ready_server.start("127.0.0.1", 0)
            try:
                code, _ = await asyncio.to_thread(_get, ready_port, "/readyz")
                assert code == 200
            finally:
                await ready_server.stop()
        finally:
            await server.stop()
    finally:
        store.close()


async def test_install_signal_handlers_without_loop_is_noop() -> None:
    await asyncio.to_thread(install_signal_handlers, lambda _name: None)
