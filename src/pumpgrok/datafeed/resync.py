"""Bounded recovery for feeds: rolling-window limiter, dedup window, gap ledger, reconnect."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from pumpgrok.events.sources import SourceSupervisor
from pumpgrok.replay.clock import Clock

TRANSPORT_FAILURES = (TimeoutError, OSError, RuntimeError)


class FrameSource(Protocol):
    async def next_frame(self) -> object: ...

    async def reconnect(self) -> None: ...


class RollingWindowLimiter:
    def __init__(self, clock: Clock, *, limit: int = 30, window_s: float = 10.0) -> None:
        raise NotImplementedError

    async def acquire(self) -> float:
        raise NotImplementedError


class DedupWindow:
    def __init__(self, *, capacity: int) -> None:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError

    def admit(self, key: tuple[str, int]) -> bool:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class Gap:
    start_ts_utc: str
    end_ts_utc: str | None
    reason: str


class GapLedger:
    def __init__(self, clock: Clock, *, capacity: int = 256) -> None:
        raise NotImplementedError

    @property
    def gaps(self) -> tuple[Gap, ...]:
        raise NotImplementedError

    @property
    def open_gap(self) -> bool:
        raise NotImplementedError

    def open(self, reason: str) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def record_loss(self, reason: str) -> None:
        raise NotImplementedError


@dataclass
class FeedStats:
    received: int = 0
    applied: int = 0
    duplicate: int = 0
    failed_tx: int = 0
    undecodable: int = 0
    unwatched: int = 0
    malformed: int = 0


class Recovery:
    def __init__(
        self,
        *,
        clock: Clock,
        supervisor: SourceSupervisor,
        frames: FrameSource,
        gaps: GapLedger,
        subscribe: Callable[[], Awaitable[None]],
        held: Callable[[], Sequence[str]],
    ) -> None:
        raise NotImplementedError

    async def receive(self) -> object | None:
        raise NotImplementedError
