"""Position watcher: polls open positions and calls the sell callback.

Port of the watcher half of the retired oracle ``src/risk.py``. All
prose is English; the vendor text is Russian.

Deliberate divergences from the oracle:

- The ``RiskManager`` dependency is replaced by a ``PositionBook``
  Protocol in this module: anything exposing ``positions``,
  ``exit_config``, ``poll_seconds``, and ``persist`` can be watched. The
  Protocol style follows ``core/datasource.py``. Phase 4 implements the
  real book; tests use a double, never ``RiskManager``.
- The poll loop sleeps on the injected clock, and ``check_once`` takes
  ``now`` explicitly.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.engine.exits import apply_price
from pumpgrok.engine.models import ExitPosition
from pumpgrok.replay.clock import Clock

log = logging.getLogger(__name__)


@runtime_checkable
class PositionBook(Protocol):
    """What the watcher needs from whoever owns the positions."""

    @property
    def positions(self) -> dict[str, ExitPosition]: ...

    @property
    def exit_config(self) -> ExitsSettings: ...

    @property
    def poll_seconds(self) -> float: ...

    def persist(self) -> None: ...


class PositionWatcher:
    """Background task: polls prices of open positions and calls sell.

    Price and sale arrive as callbacks from the outside: no RPC and no
    executor are pulled in here, so this is testable without a network.
    """

    # How much the peak must grow before it is written to disk. No point
    # persisting on every tick, but losing the peak on restart means
    # re-learning the trailing stop from the current price.
    PEAK_PERSIST_STEP = 1.01

    # This many passes in a row without a quote and the position counts
    # as blind: exit rules do not work on it, and staying silent is not
    # an option.
    BLIND_AFTER = 3

    def __init__(
        self,
        book: PositionBook,
        price_fn: Callable[[str], Awaitable[int]],
        sell_fn: Callable[[ExitPosition, int, str], Awaitable[None]],
        clock: Clock,
    ) -> None:
        self.book = book
        self.price_fn = price_fn
        self.sell_fn = sell_fn
        self.clock = clock
        self.price_failures: dict[str, int] = {}
        self._task: asyncio.Task[None] | None = None

    @property
    def blind(self) -> list[str]:
        """Positions with no quote for a while. Exits do not work on them."""
        return [
            mint
            for mint, misses in self.price_failures.items()
            if misses >= self.BLIND_AFTER and mint in self.book.positions
        ]

    async def check_once(self, now: float) -> list[str]:
        """One pass over open positions. Returns closed mints."""
        triggered: list[str] = []
        peak_grew = False
        sold = False

        for position in list(self.book.positions.values()):
            try:
                price = await self.price_fn(position.mint)
            except Exception as exc:
                log.warning("no price for %s: %s", position.mint, exc)
                price = 0
            if price <= 0:
                self._miss(position.mint)
                continue
            self.price_failures.pop(position.mint, None)

            old_peak = position.peak_price
            signal = apply_price(position, price, self.book.exit_config, now)
            if price > old_peak:
                peak_grew = peak_grew or (price >= old_peak * self.PEAK_PERSIST_STEP)
            if signal is None:
                continue

            log.info(
                "exiting %s on %s (%s): entry %.12f, now %.12f",
                position.mint[:8],
                signal.reason,
                signal.detail,
                position.entry_price,
                price,
            )
            await self.sell_fn(position, price, signal.reason)
            triggered.append(position.mint)
            sold = True

        if peak_grew or sold:
            self.book.persist()
        return triggered

    def _miss(self, mint: str) -> None:
        """Count a pass without a quote, and say so when it is too many."""
        misses = self.price_failures.get(mint, 0) + 1
        self.price_failures[mint] = misses
        if misses == self.BLIND_AFTER:
            log.error(
                "position %s without price %d passes in a row: exit rules "
                "do not work on it right now",
                mint[:8],
                misses,
            )

    async def run(self) -> None:
        interval = self.book.poll_seconds
        while True:
            try:
                await self.check_once(self.clock.now())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("position watch failed a pass: %s", exc)
            await self.clock.sleep(interval)

    def start(self) -> asyncio.Task[None]:
        self._task = asyncio.create_task(self.run(), name="position-watcher")
        return self._task

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
