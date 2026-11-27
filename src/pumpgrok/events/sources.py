"""Backoff, staleness, resync, and cursors for event sources.

This module owns those four duties inside the events package. It does not
open a socket, and it is not wired into the desk supervisor.
"""

from __future__ import annotations

import json
import math
import random
import sqlite3
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any

from pumpgrok.events.constants import (
    BACKOFF_FACTOR,
    BACKOFF_INITIAL_S,
    BACKOFF_JITTER_S,
    BACKOFF_MAX_S,
    STABLE_S,
    STALE_AFTER_S,
)
from pumpgrok.events.store import EventStore
from pumpgrok.replay.clock import Clock

CURSOR_ROW = "source"
CURSOR_SCHEMA = 1


class SourceStatus(StrEnum):
    """Connection health for one event source. Not an event catalog member."""

    live = "live"
    stale = "stale"
    resyncing = "resyncing"
    disconnected = "disconnected"


def _clean_cursor() -> dict[str, int]:
    return {"schema": CURSOR_SCHEMA}


def _backoff_exponent_cap() -> int:
    """Smallest exponent whose uncapped delay reaches BACKOFF_MAX_S.

    Clamping to it leaves every delay unchanged and keeps BACKOFF_FACTOR**step
    from overflowing during long outages.
    """
    exponent = 0
    while BACKOFF_INITIAL_S * BACKOFF_FACTOR**exponent < BACKOFF_MAX_S:
        exponent += 1
    return exponent


_BACKOFF_EXPONENT_CAP = _backoff_exponent_cap()


class SourceSupervisor:
    """Events-package owner of backoff, staleness, resync, and cursors."""

    def __init__(self, clock: Clock, rng: random.Random, *, path: str | Path) -> None:
        self._clock = clock
        self._rng = rng
        self._store = EventStore(path)
        self._step = 0
        self._healthy_since: float | None = None
        self._last_frame_at: float | None = None
        self._status = SourceStatus.live
        self._connection_generation = 0
        self._held_mints: tuple[str, ...] = ()
        self.cursor_reset = False
        self._cursor: dict[str, Any] = _clean_cursor()
        self._load_cursor()

    @property
    def last_frame_at(self) -> float | None:
        return self._last_frame_at

    @property
    def connection_generation(self) -> int:
        """Fence observations across disconnects, resyncs, and silent stale intervals."""
        return self._connection_generation

    @property
    def held_mints(self) -> tuple[str, ...]:
        return self._held_mints

    @property
    def cursor(self) -> dict[str, Any]:
        return dict(self._cursor)

    def close(self) -> None:
        self._store.close()

    def status_at(self, now: float) -> SourceStatus:
        """Stale only after silence strictly longer than the budget.

        A source that has never framed is not stale. Resync stays in force
        until the next good frame.
        """
        if self._status is SourceStatus.resyncing:
            return SourceStatus.resyncing
        if self._last_frame_at is None:
            return self._status
        if now - self._last_frame_at > STALE_AFTER_S:
            return SourceStatus.stale
        return self._status

    def note_frame(self, at: float | None = None) -> None:
        """Record one good frame. Ends resync and starts a healthy span."""
        ts = self._clock.now() if at is None else float(at)
        if not math.isfinite(ts) or (self._last_frame_at is not None and ts < self._last_frame_at):
            raise ValueError("frame timestamp must be finite and nondecreasing")
        if self._last_frame_at is not None and ts - self._last_frame_at > STALE_AFTER_S:
            self._connection_generation += 1
        self._last_frame_at = ts
        if self._healthy_since is None:
            self._healthy_since = ts
        if self._status is not SourceStatus.live:
            self._status = SourceStatus.live

    def note_failure(self) -> None:
        """Count one disconnect. A healthy span of STABLE_S or more starts a fresh backoff.

        The stability check runs before the healthy span is cleared. A stable
        span restarts at the initial step; the failure that ends it is not
        counted as a new step.
        """
        self._connection_generation += 1
        self._status = SourceStatus.disconnected
        if self._is_stable():
            self._step = 0
        else:
            self._step += 1
        self._healthy_since = None

    def next_delay_s(self) -> float:
        """Backoff step plus jitter in [0, 1). Does not sleep."""
        self._reset_if_stable()
        exponent = min(self._step, _BACKOFF_EXPONENT_CAP)
        base = min(BACKOFF_INITIAL_S * (BACKOFF_FACTOR**exponent), BACKOFF_MAX_S)
        return float(base) + self._rng.random() * BACKOFF_JITTER_S

    def resync(self, held_mints: Sequence[str]) -> None:
        """Record the caller mint list and stay resyncing until the next good frame."""
        self._connection_generation += 1
        self._held_mints = tuple(held_mints)
        self._status = SourceStatus.resyncing
        self._cursor = {**_clean_cursor(), "held_mints": list(self._held_mints)}
        self._write_cursor(self._cursor)

    def _is_stable(self) -> bool:
        if self._healthy_since is None:
            return False
        return self._clock.now() - self._healthy_since >= STABLE_S

    def _reset_if_stable(self) -> None:
        if self._is_stable():
            self._step = 0

    def _load_cursor(self) -> None:
        raw = self._read_raw()
        if raw is None:
            self._cursor = _clean_cursor()
            self._write_cursor(self._cursor)
            return
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            self._replace_corrupt()
            return
        if not isinstance(parsed, dict) or parsed.get("schema") != CURSOR_SCHEMA:
            self._replace_corrupt()
            return
        self._cursor = {"schema": CURSOR_SCHEMA}
        held = parsed.get("held_mints")
        if isinstance(held, list) and all(isinstance(item, str) for item in held):
            self._held_mints = tuple(held)
            self._cursor["held_mints"] = list(held)

    def _replace_corrupt(self) -> None:
        self.cursor_reset = True
        self._cursor = _clean_cursor()
        self._held_mints = ()
        self._write_cursor(self._cursor)

    def _read_raw(self) -> str | None:
        db = self._connect()
        try:
            row = db.execute(
                "SELECT value FROM cursors WHERE name = ?;",
                (CURSOR_ROW,),
            ).fetchone()
        finally:
            db.close()
        if row is None:
            return None
        return str(row[0])

    def _write_cursor(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True)
        db = self._connect()
        try:
            db.execute(
                "INSERT OR REPLACE INTO cursors (name, value) VALUES (?, ?);",
                (CURSOR_ROW, body),
            )
            db.commit()
        finally:
            db.close()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self._store.path))
        db.execute("PRAGMA busy_timeout = 5000;")
        return db
