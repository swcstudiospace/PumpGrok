"""Clock-driven scheduling for paper position marks.

The scheduler reads the paper adapter's existing price source and delegates all
valuation and ledger writes to its combined mark accounting path. It never
places orders. Call ``holdings_changed`` after a change to the paper book and
``close`` when the owner shuts down.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress

from pumpgrok.core.ids import Clock
from pumpgrok.datafeed.graduation import GapSettings, PositionAction, position_action
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.execution.paper_adapter.models import _ledger_mark_epoch
from pumpgrok.ledger.reducer import PositionView


class HeldMarkScheduler:
    """Mark admitted held curves at most 60 seconds apart while the book is open."""

    def __init__(
        self,
        *,
        adapter: PaperAdapter,
        clock: Clock,
        settings: GapSettings,
        max_observations: int,
    ) -> None:
        if type(max_observations) is not int or max_observations <= 0:
            raise ValueError("max_observations must be a positive integer")
        self._adapter = adapter
        self._clock = clock
        self._settings = settings
        self._next_delay = 60.0
        self._max_observations = max_observations
        self._last_trusted: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._completion: asyncio.Future[Exception | None] | None = None
        self._closed = False

    async def holdings_changed(self) -> None:
        """Reconcile and mark the current book, starting or stopping its timer.

        Capacity exhaustion raises rather than silently leaving a held mint
        unmonitored. A newly observed holding starts its gap timeout now; a
        price that fails admission never refreshes that timeout.
        """
        async with self._lifecycle_lock:
            if self._closed:
                raise RuntimeError("held mark scheduler is closed")
            if self._task is not None and self._task.done():
                task, self._task = self._task, None
                task.result()
            async with self._lock:
                held = await self._cycle()
            await self._stop_timer()
            if held:
                if self._completion is not None and self._completion.done():
                    self._completion = None
                self._completion_future()
                started = asyncio.Event()
                self._task = asyncio.create_task(self._run(started))
                self._task.add_done_callback(self._observe_task)
                await started.wait()

    async def close(self) -> None:
        """Cancel the active timer and release tracked observations."""
        async with self._lifecycle_lock:
            self._closed = True
            try:
                await self._stop_timer()
            finally:
                self._last_trusted.clear()
                completion = self._completion_future()
                if not completion.done():
                    completion.set_result(None)

    def _completion_future(self) -> asyncio.Future[Exception | None]:
        if self._completion is None:
            self._completion = asyncio.get_running_loop().create_future()
            if self._closed:
                self._completion.set_result(None)
        return self._completion

    async def wait(self) -> None:
        """Wait until shutdown or a background marking failure.

        Owners should supervise this awaitable alongside their service. Waiting
        does not start a timer, and cancelling a waiter does not stop the desk.
        """
        failure = await asyncio.shield(self._completion_future())
        if failure is not None:
            raise failure

    @staticmethod
    def _observe_task(task: asyncio.Task[None]) -> None:
        # The failure is also retained by wait(); consume the task exception so
        # asyncio does not report an unhandled task while its owner is notified.
        if not task.cancelled():
            task.exception()

    async def _stop_timer(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _run(self, started: asyncio.Event) -> None:
        started.set()
        try:
            while True:
                await self._clock.sleep(self._next_delay)
                async with self._lock:
                    if not await self._cycle():
                        return
        except Exception as exc:
            completion = self._completion_future()
            if not completion.done():
                completion.set_result(exc)
            raise

    async def _cycle(self) -> bool:
        positions = self._adapter._fold_state().positions
        mints = {
            mint for mint, pos in positions.items() if pos.token_units > 0 and not pos.mtm_frozen
        }
        if len(mints) > self._max_observations:
            raise OverflowError("held mark observation capacity exhausted")
        self._last_trusted = {
            mint: stamp for mint, stamp in self._last_trusted.items() if mint in mints
        }
        if not mints:
            return False

        now = self._clock.now()
        snapshots, zero_mints, graduated = await self._collect(positions, mints, now)
        zero_mints = self._filter_current(snapshots, zero_mints, graduated)
        # The accounting boundary independently rechecks admission.
        if snapshots or zero_mints:
            await self._adapter.mark_open_positions(snapshots=snapshots, zero_mints=zero_mints)
            for mint, snapshot in snapshots.items():
                assert snapshot.ts is not None  # guaranteed by position_action(MARK)
                self._last_trusted[mint] = snapshot.ts
        remaining = [
            stamp + self._settings.timeout_after_s - now
            for stamp in self._last_trusted.values()
            if stamp + self._settings.timeout_after_s > now
        ]
        self._next_delay = min([60.0, *remaining])
        return True

    async def _collect(
        self, positions: dict[str, PositionView], mints: set[str], now: float
    ) -> tuple[dict[str, CurveSnapshot], set[str], dict[str, CurveSnapshot]]:
        snapshots: dict[str, CurveSnapshot] = {}
        zero_mints: set[str] = set()
        graduated: dict[str, CurveSnapshot] = {}
        for mint in sorted(mints):
            last_trusted_at = self._last_trusted.setdefault(mint, now)
            snapshot = await self._adapter._read_curve(mint)
            if snapshot is not None and snapshot.mint != mint:
                snapshot = None
            action = position_action(
                snapshot, last_trusted_at=last_trusted_at, now=now, settings=self._settings
            )
            if action is PositionAction.MARK and snapshot is not None:
                snapshots[mint] = snapshot
            elif action is PositionAction.GRADUATED and snapshot is not None:
                graduated[mint] = snapshot
            elif action is PositionAction.ZERO_MARK and positions[mint].mtm_source != "timeout":
                zero_mints.add(mint)
        return snapshots, zero_mints, graduated

    def _filter_current(
        self,
        snapshots: dict[str, CurveSnapshot],
        zero_mints: set[str],
        graduated: dict[str, CurveSnapshot],
    ) -> set[str]:
        # Source reads can suspend while holdings and ledger marks change.
        current = self._adapter._fold_state().positions
        for mint, snapshot in list(snapshots.items()):
            pos = current.get(mint)
            if pos is None or pos.token_units <= 0 or pos.mtm_frozen:
                del snapshots[mint]
                continue
            ledger_time = _ledger_mark_epoch(pos)
            cached_time = self._adapter._last_price_ts.get(mint)
            assert snapshot.ts is not None
            if (ledger_time is not None and snapshot.ts < ledger_time) or (
                cached_time is not None and snapshot.ts < cached_time
            ):
                del snapshots[mint]
        zero_mints = {
            mint
            for mint in zero_mints
            if mint in current
            and current[mint].token_units > 0
            and not current[mint].mtm_frozen
            and current[mint].mtm_source != "timeout"
        }
        for mint, snapshot in graduated.items():
            if mint in current and current[mint].token_units > 0 and not current[mint].mtm_frozen:
                assert snapshot.ts is not None
                self._last_trusted[mint] = max(self._last_trusted[mint], snapshot.ts)
        return zero_mints
