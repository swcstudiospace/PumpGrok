"""Bounded watch set: held mints are pinned, candidates overflow deterministically."""

from __future__ import annotations


class WatchSet:
    def __init__(self, *, max_watched_mints: int) -> None:
        raise NotImplementedError

    @property
    def capacity(self) -> int:
        raise NotImplementedError

    @property
    def held(self) -> tuple[str, ...]:
        raise NotImplementedError

    @property
    def candidates(self) -> tuple[str, ...]:
        raise NotImplementedError

    @property
    def degraded(self) -> bool:
        raise NotImplementedError

    @property
    def overflow(self) -> int:
        raise NotImplementedError

    @property
    def displaced(self) -> int:
        raise NotImplementedError

    @property
    def refused_held(self) -> int:
        raise NotImplementedError

    def __contains__(self, mint: object) -> bool:
        raise NotImplementedError

    def admit_candidate(self, mint: str) -> bool:
        raise NotImplementedError

    def pin(self, mint: str) -> bool:
        raise NotImplementedError

    def release(self, mint: str) -> None:
        raise NotImplementedError
