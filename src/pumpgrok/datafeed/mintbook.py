"""Bounded mint book: records exist only for mints the watch set currently holds."""

from __future__ import annotations

from dataclasses import dataclass

from pumpgrok.datafeed.watchset import WatchSet

STAGE_CREATED = "created"
STAGE_MIGRATED = "migrated"


@dataclass(frozen=True, slots=True)
class MintRecord:
    mint: str
    stage: str
    stage_ts_utc: str


class MintBook:
    """Creation and migration stage for watched mints.

    The watch set owns admission and capacity. Records are pruned whenever the watch
    set no longer holds their mint, so the book never holds more entries than the cap.
    """

    def __init__(self, *, watch: WatchSet) -> None:
        self._watch = watch
        self._records: dict[str, MintRecord] = {}

    def _prune(self) -> None:
        for mint in [mint for mint in self._records if mint not in self._watch]:
            del self._records[mint]

    def __len__(self) -> int:
        self._prune()
        return len(self._records)

    @property
    def held(self) -> tuple[str, ...]:
        return self._watch.held

    def admit_created(self, mint: str, ts_utc: str) -> bool:
        """Watch a newly created mint. A repeated creation keeps its first record."""
        self._prune()
        if mint in self._records:
            return True
        if not self._watch.admit_candidate(mint):
            return False
        self._records[mint] = MintRecord(mint=mint, stage=STAGE_CREATED, stage_ts_utc=ts_utc)
        return True

    def mark_migrated(self, mint: str, ts_utc: str) -> bool:
        """Advance a watched mint to migrated. Unwatched mints are not recorded."""
        self._prune()
        if mint not in self._watch:
            return False
        self._records[mint] = MintRecord(mint=mint, stage=STAGE_MIGRATED, stage_ts_utc=ts_utc)
        return True

    def record(self, mint: str) -> MintRecord | None:
        self._prune()
        return self._records.get(mint)

    def release(self, mint: str) -> None:
        self._watch.release(mint)
        self._prune()
