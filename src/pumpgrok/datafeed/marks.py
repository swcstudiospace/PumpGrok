"""Held-mint marks on the injected Clock (MKT-08, T-13-02b).

Clock-driven poll: each held mint gets a mark within 60 s of needing one.
An empty book means no timer at all. No asyncio, no wall time.
"""

from __future__ import annotations

from collections.abc import Callable

from pumpgrok.datafeed.mintbook import MintBook
from pumpgrok.replay.clock import FixtureClock, WallClock

MARK_INTERVAL_S = 60.0

PriceProvider = Callable[[str], int | None]
MarkSink = Callable[[str, int | None], None]


class MarksLoop:
    """Marks every held mint on a 60 s cadence driven by the injected Clock."""

    def __init__(
        self,
        book: MintBook,
        clock: FixtureClock | WallClock,
        price: PriceProvider,
        on_mark: MarkSink,
    ) -> None:
        self._book = book
        self._clock = clock
        self._price = price
        self._on_mark = on_mark
        self._last_mark: dict[str, float] = {}

    @property
    def scheduled(self) -> bool:
        """True while any mint is held (a timer would exist); False when flat."""
        return len(self._book) > 0

    def next_deadline(self) -> float | None:
        """Next epoch a mark is due, or None when flat (no timer)."""
        if len(self._book) == 0:
            return None
        due = [
            self._last_mark.get(mint, self._clock.now() - MARK_INTERVAL_S) + MARK_INTERVAL_S
            for mint in self._book.held()
        ]
        return min(due) if due else None

    def poll(self) -> tuple[str, ...]:
        """Emit marks for mints due; return the marked mints. Flat: no-op."""
        now = self._clock.now()
        marked: list[str] = []
        for mint in sorted(self._book.held()):
            last = self._last_mark.get(mint, now - MARK_INTERVAL_S)
            if now - last >= MARK_INTERVAL_S:
                self._on_mark(mint, self._price(mint))
                self._last_mark[mint] = now
                marked.append(mint)
        return tuple(marked)
