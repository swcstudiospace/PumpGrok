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
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    async def holdings_changed(self) -> None:
        """Reconcile and mark the current book, starting or stopping its timer.

        Capacity exhaustion raises rather than silently leaving a held mint
        unmonitored. A newly observed holding starts its gap timeout now; a
        price that fails admission never refreshes that timeout.
        """
        if self._closed:
            raise RuntimeError("held mark scheduler is closed")
        if self._task is not None and self._task.done():
            self._task.result()
            self._task = None
        async with self._lock:
            held = await self._cycle()
        await self._stop_timer()
        if held:
            started = asyncio.Event()
            self._task = asyncio.create_task(self._run(started))
            await started.wait()

    async def close(self) -> None:
        """Cancel the active timer and release tracked observations."""
        self._closed = True
        try:
            await self._stop_timer()
        finally:
            self._last_trusted.clear()

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
        while True:
            await self._clock.sleep(self._next_delay)
            async with self._lock:
                if not await self._cycle():
                    return

    async def _cycle(self) -> bool:
        positions = await self._adapter.positions()
        mints = {position.mint for position in positions if not position.mtm_frozen}
        if len(mints) > self._max_observations:
            raise OverflowError("held mark observation capacity exhausted")
        self._last_trusted = {
            mint: stamp for mint, stamp in self._last_trusted.items() if mint in mints
        }
        if not mints:
            return False

        now = self._clock.now()
        snapshots: dict[str, CurveSnapshot] = {}
        zero_mints: set[str] = set()
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
            elif action is PositionAction.ZERO_MARK:
                zero_mints.add(mint)

        # This path rechecks admission at the accounting boundary and folds
        # holdings again. Unavailable mints are omitted, retaining their marks.
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
