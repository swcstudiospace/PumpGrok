"""FixtureClock-driven event source over a recorded dataset (BT-12; D-04).

The source yields verified dataset events in manifest order and answers
point-in-time tick lookups through a per-mint bisect index, so a lookup
costs O(log n) in that mint's tick count instead of a full scan. Time
moves only through :class:`pumpgrok.replay.clock.FixtureClock`: the
caller advances the clock and the source never reads the host clock.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterator
from typing import Any

from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import FixtureDataset, event_epoch

__all__ = ["DatasetEventSource"]


class DatasetEventSource:
    """Events of one recorded dataset with a per-mint bisect index."""

    def __init__(self, dataset: FixtureDataset, clock: FixtureClock) -> None:
        self._dataset = dataset
        self._clock = clock
        self._stamps: list[float] = [event_epoch(event) for event in dataset.events]
        per_mint: dict[str, list[tuple[float, int]]] = {}
        for index, event in enumerate(dataset.events):
            mint = event.get("mint")
            if isinstance(mint, str):
                per_mint.setdefault(mint, []).append((self._stamps[index], index))
        self._mint_stamps: dict[str, list[float]] = {
            mint: [stamp for stamp, _ in ticks] for mint, ticks in per_mint.items()
        }
        self._mint_positions: dict[str, list[int]] = {
            mint: [index for _, index in ticks] for mint, ticks in per_mint.items()
        }

    @property
    def clock(self) -> FixtureClock:
        """The virtual clock driving this source."""
        return self._clock

    def __len__(self) -> int:
        return len(self._dataset.events)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._dataset.events)

    def tick_at(self, mint: str, ts: float) -> dict[str, Any] | None:
        """Latest event for ``mint`` at or before ``ts`` (bisect, O(log n))."""
        stamps = self._mint_stamps.get(mint)
        if not stamps:
            return None
        position = bisect.bisect_right(stamps, ts) - 1
        if position < 0:
            return None
        return self._dataset.events[self._mint_positions[mint][position]]

    def advance_to(self, ts: float) -> dict[str, Any] | None:
        """Advance the fixture clock and return the events now due as a marker.

        Returns the latest event at or before ``ts`` across every mint, or
        None when nothing is due yet. The clock never moves backwards.
        """
        self._clock.advance_to(ts)
        position = bisect.bisect_right(self._stamps, ts) - 1
        if position < 0:
            return None
        return self._dataset.events[position]
