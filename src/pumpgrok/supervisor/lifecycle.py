"""Shutdown and signal handling (paper-engine.md 6.5).

Ports of the vendor ops helpers (``ops.py:372-440``): ``drain`` waits for
running cycles with a virtual-time grace, ``install_signal_handlers`` maps
SIGINT/SIGTERM to an orderly stop, and ``cancel_and_wait`` drops one task
without leaking ``CancelledError``. ``shutdown`` stops scheduling, drains
within 30 s, writes a ledger snapshot, flushes the JSONL export, writes
``var/health.json`` with ``status=stopped``, and returns 0.

Second signal never forces: ``request_stop`` is idempotent and only logs.
A hard kill mid-append stays consistent via the 04-01 batch rollback
(sqlite WAL, ``synchronous=FULL``, ``BEGIN IMMEDIATE``).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from pumpgrok.core.ids import Clock
from pumpgrok.ledger.export import export_ledger
from pumpgrok.ledger.reducer import dump_state, initial_state, reduce
from pumpgrok.replay.clock import format_ts_utc
from pumpgrok.supervisor.health import write_health_json

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore
    from pumpgrok.supervisor.scheduler import Supervisor

log = logging.getLogger(__name__)

#: Drain grace for running cycles (vendor ops.shutdown_grace_seconds).
SHUTDOWN_GRACE_S = 30.0


def install_signal_handlers(stop: Callable[[str], None]) -> None:
    """Map SIGINT/SIGTERM to an orderly stop (vendor semantics)."""

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop, sig.name)
        except NotImplementedError:  # Windows: fall back to signal.signal
            signal.signal(sig, lambda *_args, name=sig.name: stop(name))


async def drain(tasks: set[asyncio.Task[Any]], grace_s: float, clock: Clock) -> tuple[int, int]:
    """Wait for running tasks up to the virtual grace, then cancel stragglers.

    Returns ``(finished, cancelled)`` like the vendor helper. The grace is
    a ``clock.sleep``, so replay determinism holds; ``asyncio.wait`` is
    used without a timeout (never a time source).
    """
    live = {task for task in tasks if not task.done()}
    if not live:
        return 0, 0
    log.info("stopping: waiting for %d tasks up to %.0fs", len(live), grace_s)
    waiter = asyncio.ensure_future(asyncio.wait(live))
    sleeper = asyncio.ensure_future(clock.sleep(grace_s))
    try:
        done, _ = await asyncio.wait({waiter, sleeper}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        if not sleeper.done():
            sleeper.cancel()
    if waiter in done:
        with contextlib.suppress(asyncio.CancelledError):
            await waiter
        finished = sum(1 for task in live if task.done() and not task.cancelled())
        return finished, 0
    waiter.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await waiter
    stragglers = [task for task in live if not task.done()]
    for task in stragglers:
        task.cancel()
    if stragglers:
        await asyncio.gather(*stragglers, return_exceptions=True)
        log.warning("%d tasks exceeded grace and were cancelled", len(stragglers))
    finished = sum(1 for task in live if task.done() and not task.cancelled())
    return finished, len(stragglers)


async def cancel_and_wait(task: asyncio.Task[Any] | None) -> None:
    """Cancel one task and wait for it, swallowing ``CancelledError``."""
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def shutdown(
    supervisor: Supervisor,
    *,
    store: LedgerStore,
    health_path: str,
    journal_dir: str,
    trades_path: str,
    grace_s: float = SHUTDOWN_GRACE_S,
) -> int:
    """Orderly shutdown: stop, drain, snapshot, export, stopped health, 0."""
    supervisor.request_stop("shutdown")
    running = supervisor.running_tasks()
    finished, cancelled = await drain(set(running), grace_s, supervisor.clock)
    log.info("drain finished=%d cancelled=%d", finished, cancelled)

    clock = supervisor.clock
    ts_utc = format_ts_utc(clock.now())
    try:
        head = store.read(since_seq=1, limit=None)
        if head:
            first = head[0]
            meta_source = store.get_meta("source")
            genesis = initial_state(
                source=meta_source or str(first.get("source", "paper")),
                initial_equity_lamports=int(store.get_meta("initial_equity_lamports") or 0),
                day_utc=str(first.get("ts_utc", ""))[:10],
            )
        else:
            genesis = initial_state(source="paper", initial_equity_lamports=0, day_utc="")
        state = genesis
        for event in head:
            state = reduce(state, event)
        body = dump_state(state)
        body["meta"] = {"status": "stopped", "ts_utc": ts_utc}
        last_seq = int(head[-1]["seq"]) if head else 0
        store.write_snapshot(seq=last_seq, ts_utc=ts_utc, state=body)
    except Exception as exc:
        log.warning("shutdown snapshot failed: %s", exc)
    try:
        export_ledger(store, journal_dir=journal_dir, trades_path=trades_path)
    except Exception as exc:
        log.warning("shutdown export flush failed: %s", exc)
    try:
        status = supervisor.health_status()
        status["status"] = "stopped"
        write_health_json(health_path, status)
    except Exception as exc:
        log.warning("shutdown health write failed: %s", exc)
    _notify_stopped(supervisor)
    return 0


def _notify_stopped(supervisor: Supervisor) -> None:
    """Best-effort stopped notice; open positions are called out by the log."""
    try:
        status = supervisor.health_status()
    except Exception:
        return
    if int(status.get("open_positions", 0)) > 0:
        log.warning(
            "stopped with %s open positions; stop rules do not run while down",
            status.get("open_positions"),
        )
    log.info("supervisor stopped")
