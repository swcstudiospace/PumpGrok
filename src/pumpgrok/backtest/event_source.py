"""Per-mint bisect index over a dataset's tick events (BT-12).

Events are merged by ``(ts, file_order, line_no)``, the order in paper-engine.md.
A window query bisects one mint's sorted timestamps. It does not scan other mints.
``_examine`` is the instrumentation point: a lookup calls it once per timestamp the
bisect probes, so a test can count events examined without a wall-clock assertion.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pumpgrok.replay.clock import Clock
from pumpgrok.replay.fixtures import event_epoch, load_dataset

__all__ = ["DatasetCurveSource"]

_Row = tuple[float, Mapping[str, Any]]


def _stamp(event: Mapping[str, Any]) -> float:
    """Epoch seconds: a leading ``ts``, or the fixture ``ts_utc`` when that is absent."""
    raw = event.get("ts")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return event_epoch(dict(event))
    return float(raw)


def _merge_key(event: Mapping[str, Any], index: int) -> tuple[float, int, int]:
    """The recorder merge key. Missing file order keeps the input position."""
    file_order = event.get("file_order", 0)
    line_no = event.get("line_no", index)
    return (_stamp(event), int(file_order), int(line_no))


class DatasetCurveSource:
    """Tick events in merge order, indexed per mint for window queries."""

    def __init__(
        self, events: Sequence[Mapping[str, Any]], *, clock: Clock | None = None
    ) -> None:
        ordered = sorted(enumerate(events), key=lambda item: _merge_key(item[1], item[0]))
        self._events: tuple[Mapping[str, Any], ...] = tuple(event for _, event in ordered)
        by_mint: dict[str, list[_Row]] = {}
        for event in self._events:
            mint = str(event.get("mint", ""))
            by_mint.setdefault(mint, []).append((_stamp(event), event))
        self._by_mint: dict[str, tuple[_Row, ...]] = {
            mint: tuple(rows) for mint, rows in by_mint.items()
        }
        self._clock = clock
        self.events_examined = 0

    @classmethod
    def from_dataset(
        cls, dataset_dir: str | Path, *, clock: Clock | None = None
    ) -> DatasetCurveSource:
        """Load a verified fixture directory and index its tick events."""
        dataset = load_dataset(Path(dataset_dir))
        return cls(dataset.events, clock=clock)

    @property
    def events(self) -> tuple[Mapping[str, Any], ...]:
        """Every tick in merge order."""
        return self._events

    def _examine(self, stamp: float) -> float:
        """Count one timestamp probe. Tests override this to instrument a lookup."""
        self.events_examined += 1
        return stamp

    def _stamp_of(self, row: _Row) -> float:
        return self._examine(row[0])

    def window(self, mint: str, start: float, end: float) -> tuple[Mapping[str, Any], ...]:
        """Events for one mint with timestamps in ``[start, end]``, in merge order.

        The lookup bisects that mint's sorted timestamps. A mint with no ticks,
        or a reversed range, examines nothing and returns empty.
        """
        series = self._by_mint.get(str(mint))
        if not series or start > end:
            return ()
        left = bisect_left(series, start, key=self._stamp_of)
        right = bisect_right(series, end, key=self._stamp_of)
        return tuple(row[1] for row in series[left:right])

    def latest(self, mint: str, at: float) -> Mapping[str, Any] | None:
        """The latest event for one mint at or before ``at``, or None."""
        series = self._by_mint.get(str(mint))
        if not series:
            return None
        index = bisect_right(series, at, key=self._stamp_of) - 1
        if index < 0:
            return None
        return series[index][1]
