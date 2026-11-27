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

import contextlib
import json
import os
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

from pumpgrok.core.budget import utc_day
from pumpgrok.core.errors import PumpgrokError
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.replay.clock import Clock

MINUTE_LIMIT = 6
HOUR_LIMIT = 60
DAY_LIMIT = 400
RESERVE_PERCENT = 20

# SQLite lock-wait budget between handles. Real-time lock wait, not a clock read.
_BUSY_TIMEOUT_S = 5.0


class BudgetExhausted(RuntimeError):
    """A debit was refused because a cap would be exceeded."""


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
    """Minute, hour and day Grok call caps, persisted and charged atomically.

    Two construction styles share one class, matching both callers in the
    tree: ``LayeredBudget(path, clock)`` opens the sidecar SQLite store whose
    ``try_charge`` / ``usage`` charge the three layers all-or-nothing, while
    ``LayeredBudget(window_cap=..., agent_cap=..., global_cap=...,
    path=...)`` keeps per-window, per-agent and global caps in memory under
    a lock, persisted restart-safe in the sidecar pattern (tmp write plus
    os.replace) and charged through ``try_debit``.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        clock: Clock | None = None,
        *,
        window_cap: int = 100,
        agent_cap: int = 40,
        global_cap: int = 200,
        reserve_share_num: int = 1,
        reserve_share_den: int = 4,
    ) -> None:
        self._path = Path(path) if path is not None else None
        self._clock = clock
        if clock is not None:
            con = self._open()
            con.close()
            return
        self._window_cap = window_cap
        self._agent_cap = agent_cap
        self._global_cap = global_cap
        self._reserve_share_num = reserve_share_num
        self._reserve_share_den = reserve_share_den
        self._lock = threading.Lock()
        self._window_spent = 0
        self._global_spent = 0
        self._agent_spent: dict[str, int] = {}
        self._load()

    @property
    def window_spent(self) -> int:
        return self._window_spent

    @property
    def global_spent(self) -> int:
        return self._global_spent

    def spent_for(self, agent: str) -> int:
        return self._agent_spent.get(agent, 0)

    def _non_reserve_cap(self) -> int:
        kept = self._window_cap * self._reserve_share_num // self._reserve_share_den
        return self._window_cap - kept

    def try_debit(self, agent: str, cost: int = 1, *, use_reserve: bool = False) -> bool:
        """Atomically debit all three layers. Returns False without side effects."""
        if cost < 1:
            raise ValueError("cost must be at least 1")
        with self._lock:
            window_cap = self._window_cap if use_reserve else self._non_reserve_cap()
            if self._window_spent + cost > window_cap:
                return False
            if self._agent_spent.get(agent, 0) + cost > self._agent_cap:
                return False
            if self._global_spent + cost > self._global_cap:
                return False
            self._window_spent += cost
            self._global_spent += cost
            self._agent_spent[agent] = self._agent_spent.get(agent, 0) + cost
            self._persist_locked()
            return True

    def _persist_locked(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "window_spent": self._window_spent,
            "global_spent": self._global_spent,
            "agent_spent": dict(self._agent_spent),
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(canonical_json(body), encoding="utf-8")
        os.replace(tmp, self._path)

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            body = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self._window_spent = int(body.get("window_spent", 0))
        self._global_spent = int(body.get("global_spent", 0))
        raw = body.get("agent_spent", {})
        self._agent_spent = {str(k): int(v) for k, v in dict(raw).items()}

    def _open(self) -> sqlite3.Connection:
        try:
            assert self._path is not None
            con = sqlite3.connect(self._path, timeout=_BUSY_TIMEOUT_S, isolation_level=None)
            con.execute(_SCHEMA)
        except sqlite3.Error as exc:
            raise BudgetUnavailable(f"grok budget store unavailable: {exc}") from exc
        return con

    def try_charge(self, *, reserve_priority: bool) -> bool:
        """Spend one call on every layer, or none. False means a layer is full."""
        assert self._clock is not None
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
        assert self._clock is not None
        now = self._clock.now()
        con = self._open()
        try:
            return {name: _spent(con, name, window_of(now)) for name, _limit, window_of in LAYERS}
        except sqlite3.Error as exc:
            raise BudgetUnavailable(f"grok budget read failed: {exc}") from exc
        finally:
            con.close()


def _spent(con: sqlite3.Connection, layer: str, window: str) -> int:
    row = con.execute("SELECT window, spent FROM grok_budget WHERE layer = ?", (layer,)).fetchone()
    if row is None or row[0] != window:
        return 0
    return int(row[1])


def _rollback_quietly(con: sqlite3.Connection) -> None:
    with contextlib.suppress(sqlite3.Error):
        con.execute("ROLLBACK")
