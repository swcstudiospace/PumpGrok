"""Ordered fixture event source (paper-engine.md 4.3, PAPER-004).

Thin view over a verified :class:`FixtureDataset`: events are already
sha256-checked and ts_utc-ordered by :func:`load_dataset`, so the source only
exposes them in stored order plus their epoch stamps for the runner clock.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pumpgrok.replay.fixtures import FixtureDataset, event_epoch

__all__ = ["FixtureEventSource"]


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
