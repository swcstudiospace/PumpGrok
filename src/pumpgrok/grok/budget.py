"""Layered persisted budget (GRK-07, T-14-01-04).

Per-window, per-agent, and global caps with an atomic reserve-aware debit
under a lock, persisted restart-safe in the sidecar pattern (tmp write plus
os.replace). Exhausted budget fails closed with a typed error.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from pumpgrok.core.idempotency import canonical_json


class BudgetExhausted(RuntimeError):
    """A debit was refused because a cap would be exceeded."""


class LayeredBudget:
    def __init__(
        self,
        *,
        window_cap: int = 100,
        agent_cap: int = 40,
        global_cap: int = 200,
        reserve_share_num: int = 1,
        reserve_share_den: int = 4,
        path: Path | None = None,
    ) -> None:
        self._window_cap = window_cap
        self._agent_cap = agent_cap
        self._global_cap = global_cap
        self._reserve_share_num = reserve_share_num
        self._reserve_share_den = reserve_share_den
        self._path = path
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
