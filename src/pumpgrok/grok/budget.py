"""Layered, persisted Grok call budget (GRK-04; Design A sections 6 and 7).

Three layers (minute, hour, UTC day) are charged all-or-nothing in one
``BEGIN IMMEDIATE`` transaction on a sidecar SQLite file. A restart, or a
second process on the same file, sees the same counts. A layer whose stored
window differs from the current window starts again at zero.

The reserve share is held back from ordinary callers: they may spend only the
limit minus the reserve. Reserve-priority callers may spend the full limit.

An unreadable or unwritable store raises ``BudgetUnavailable``. Callers must
treat that as a refusal to spend, never as a free call.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from pumpgrok.core.budget import utc_day
from pumpgrok.core.errors import PumpgrokError
from pumpgrok.replay.clock import Clock

MINUTE_LIMIT = 6
HOUR_LIMIT = 60
DAY_LIMIT = 400
RESERVE_PERCENT = 20

# SQLite lock-wait budget between handles. Real-time lock wait, not a clock read.
_BUSY_TIMEOUT_S = 5.0


class BudgetUnavailable(PumpgrokError):
    """The persisted budget could not be read or written; no spend may follow."""

    code = "grok_budget_unavailable"


def reserve_slots(limit: int) -> int:
    """Calls held back from ordinary callers: ceil(limit x RESERVE_PERCENT / 100)."""
    return -(-limit * RESERVE_PERCENT // 100)


def _minute_window(now: float) -> str:
    return str(int(now // 60))


def _hour_window(now: float) -> str:
    return str(int(now // 3600))


# (layer name, limit, window identity for an epoch second)
LAYERS: tuple[tuple[str, int, Callable[[float], str]], ...] = (
    ("minute", MINUTE_LIMIT, _minute_window),
    ("hour", HOUR_LIMIT, _hour_window),
    ("day", DAY_LIMIT, utc_day),
)

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS grok_budget ("
    " layer TEXT PRIMARY KEY,"
    " window TEXT NOT NULL,"
    " spent INTEGER NOT NULL CHECK (spent >= 0))"
)


class LayeredBudget:
    """Minute, hour and day Grok call caps, persisted and charged atomically."""

    def __init__(self, path: str | Path, clock: Clock) -> None:
        self._path = Path(path)
        self._clock = clock
        con = self._open()
        con.close()

    def _open(self) -> sqlite3.Connection:
        try:
            con = sqlite3.connect(self._path, timeout=_BUSY_TIMEOUT_S, isolation_level=None)
            con.execute(_SCHEMA)
        except sqlite3.Error as exc:
            raise BudgetUnavailable(f"grok budget store unavailable: {exc}") from exc
        return con

    def try_charge(self, *, reserve_priority: bool) -> bool:
        """Spend one call on every layer, or none. False means a layer is full."""
        now = self._clock.now()
        con = self._open()
        try:
            con.execute("BEGIN IMMEDIATE")
            charged = self._charge_in_transaction(con, now, reserve_priority=reserve_priority)
            con.execute("COMMIT" if charged else "ROLLBACK")
            return charged
        except sqlite3.Error as exc:
            _rollback_quietly(con)
            raise BudgetUnavailable(f"grok budget charge failed: {exc}") from exc
        finally:
            con.close()

    def _charge_in_transaction(
        self, con: sqlite3.Connection, now: float, *, reserve_priority: bool
    ) -> bool:
        plan: list[tuple[str, str, int]] = []
        for name, limit, window_of in LAYERS:
            window = window_of(now)
            spent = _spent(con, name, window)
            cap = limit if reserve_priority else limit - reserve_slots(limit)
            if spent + 1 > cap:
                return False
            plan.append((name, window, spent + 1))
        con.executemany(
            "INSERT INTO grok_budget (layer, window, spent) VALUES (?, ?, ?)"
            " ON CONFLICT (layer) DO UPDATE SET window = excluded.window, spent = excluded.spent",
            plan,
        )
        return True

    def usage(self) -> dict[str, int]:
        """Calls spent in each layer's current window, for operator reads and tests."""
        now = self._clock.now()
        con = self._open()
        try:
            return {
                name: _spent(con, name, window_of(now)) for name, _limit, window_of in LAYERS
            }
        except sqlite3.Error as exc:
            raise BudgetUnavailable(f"grok budget read failed: {exc}") from exc
        finally:
            con.close()


def _spent(con: sqlite3.Connection, layer: str, window: str) -> int:
    row = con.execute(
        "SELECT window, spent FROM grok_budget WHERE layer = ?", (layer,)
    ).fetchone()
    if row is None or row[0] != window:
        return 0
    return int(row[1])


def _rollback_quietly(con: sqlite3.Connection) -> None:
    try:
        con.execute("ROLLBACK")
    except sqlite3.Error:
        pass
