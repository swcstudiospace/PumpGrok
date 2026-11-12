"""Bounded mint book: records exist only for mints the watch set currently holds."""

from __future__ import annotations

from dataclasses import dataclass

from pumpgrok.datafeed.watchset import WatchSet


@dataclass(frozen=True, slots=True)
class MintRecord:
    mint: str
    stage: str
    stage_ts_utc: str


class MintBook:
    def __init__(self, *, watch: WatchSet) -> None:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError

    def admit_created(self, mint: str, ts_utc: str) -> bool:
        raise NotImplementedError

    def mark_migrated(self, mint: str, ts_utc: str) -> bool:
        raise NotImplementedError

    def record(self, mint: str) -> MintRecord | None:
        raise NotImplementedError

    def release(self, mint: str) -> None:
        raise NotImplementedError
