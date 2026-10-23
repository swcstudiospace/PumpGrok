"""Ordered fixture event source and fixture curve reads (paper-engine.md 4.3, PAPER-004).

:class:`FixtureEventSource` is a thin view over a verified
:class:`FixtureDataset`: events are already sha256-checked and ts_utc-ordered
by :func:`load_dataset`. :class:`FixtureCurveSource` binds the paper adapter's
curve reads to those same ticks: the latest tick for a mint at or before the
virtual clock, so a fill and its risk check price from recorded reserves only.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pumpgrok.core.ids import Clock
from pumpgrok.execution.paper_adapter import CurveSnapshot
from pumpgrok.replay.fixtures import FixtureDataset, event_epoch

__all__ = ["FixtureCurveSource", "FixtureEventSource"]


class FixtureEventSource:
    """Yield verified fixture events in manifest order."""

    def __init__(self, dataset: FixtureDataset) -> None:
        self._dataset = dataset

    @property
    def name(self) -> str:
        """Dataset name from the manifest."""
        return self._dataset.manifest.dataset

    def __len__(self) -> int:
        return len(self._dataset.events)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._dataset.events)

    def timestamps(self) -> list[float]:
        """Epoch stamp of every event, in stored order."""
        return [event_epoch(event) for event in self._dataset.events]


class FixtureCurveSource:
    """Curve reads from fixture ticks: the latest tick per mint at or before ``now``.

    Satisfies the paper adapter's ``PriceSource`` protocol and the synchronous
    reserves lookup the risk engine uses. A tick without integer reserves never
    prices; a mint with no tick at or before ``now`` has no curve (fail closed).
    """

    def __init__(self, dataset: FixtureDataset, clock: Clock) -> None:
        self._clock = clock
        self._ticks = [
            (event_epoch(event), event) for event in dataset.events if _has_reserves(event)
        ]

    def _latest(self, mint: str) -> CurveSnapshot | None:
        now = self._clock.now()
        best: dict[str, Any] | None = None
        for stamp, event in self._ticks:
            if stamp > now:
                break
            if event.get("mint") == mint:
                best = event
        if best is None:
            return None
        return CurveSnapshot(
            mint=mint,
            s_lamports=int(best["S"]),
            t_units=int(best["T"]),
            complete=bool(best.get("complete", False)),
            source="fixture",
        )

    async def curve(self, mint: str) -> CurveSnapshot | None:
        """Adapter curve read at the current virtual time."""
        return self._latest(mint)

    def reserves(self, mint: str) -> tuple[int, int] | None:
        """Synchronous ``(sol_lamports, token_units)`` for the risk liquidity floor."""
        snapshot = self._latest(mint)
        if snapshot is None:
            return None
        return snapshot.s_lamports, snapshot.t_units

    def last_open_reserves(self, mint: str) -> tuple[int, int] | None:
        """Reserves of the latest tick at or before ``now`` that still had the curve open.

        A graduated position closes at these reserves, the last price before the curve
        completed (``close_on_graduation``). None when no open tick exists yet.
        """
        now = self._clock.now()
        best: dict[str, Any] | None = None
        for stamp, event in self._ticks:
            if stamp > now:
                break
            if event.get("mint") == mint and not event.get("complete", False):
                best = event
        if best is None:
            return None
        return int(best["S"]), int(best["T"])


def _has_reserves(event: dict[str, Any]) -> bool:
    for key in ("S", "T"):
        value = event.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            return False
    return True
