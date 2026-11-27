"""Degraded-mode probes and behavior switches (paper-engine.md 6.7)."""

from __future__ import annotations

import logging
import os
import weakref
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.risk.killswitch import env_engaged

log = logging.getLogger("pumpgrok.supervisor.scheduler")

#: Bounded buffer for orders while the ledger is unwritable (paper-engine.md 6.7).
LEDGER_BUFFER_CAP = 1000


@dataclass(frozen=True)
class LedgerLatches:
    """Health latches folded from the ledger: kill switch, desk halt and breaker states.

    ``kill_event`` is the type of the newest kill-switch row (``KillSwitchSet`` or
    ``KillSwitchCleared``), or None when the ledger holds none.
    """

    kill_event: str | None
    halted: bool
    breakers: Mapping[str, str]


@dataclass
class _LatchCursor:
    """Fold position over one store: every row up to ``seq`` is already folded."""

    seq: int = 0
    kill_event: str | None = None
    halted: bool = False
    breakers: dict[str, str] = field(default_factory=dict)


#: One cursor per open store, so a probe folds only the rows appended since the previous probe.
_CURSORS: weakref.WeakKeyDictionary[LedgerStore, _LatchCursor] = weakref.WeakKeyDictionary()


def fold_latches(store: LedgerStore) -> LedgerLatches:
    """Fold the health latches from the rows appended since the previous call on this store.

    Incremental: a probe reads only the rows past its cursor, never the whole ledger.
    """
    cursor = _CURSORS.get(store)
    if cursor is None:
        cursor = _LatchCursor()
        _CURSORS[store] = cursor
    for event in store.read(since_seq=cursor.seq + 1, limit=None):
        cursor.seq = int(event["seq"])
        event_type = event.get("type")
        payload = event.get("payload")
        row = payload if isinstance(payload, Mapping) else {}
        if event_type in ("KillSwitchSet", "KillSwitchCleared"):
            cursor.kill_event = str(event_type)
        elif event_type == "HaltSet":
            cursor.halted = True
        elif event_type == "HaltCleared":
            cursor.halted = False
        elif event_type in ("BreakerTripped", "BreakerReset"):
            name = str(row.get("breaker", "unknown"))
            cursor.breakers[name] = "open" if event_type == "BreakerTripped" else "closed"
    return LedgerLatches(
        kill_event=cursor.kill_event,
        halted=cursor.halted,
        breakers=dict(cursor.breakers),
    )


def kill_switch_engaged(store: LedgerStore) -> bool:
    """Shared kill-switch latch for the health body and the metrics gauge.

    True when the newest ``KillSwitchSet`` row has no later ``KillSwitchCleared``, or
    when ``PUMPGROK_KILLSWITCH`` engages in this process (fail-closed, same
    fold as ``run_halt_status``). File and alert-command sources are enforced
    at decision time by the risk engine; unreadable ledgers report engaged
    rather than all-clear. ``health_status`` and the serve ``_snapshot`` both
    read this so the body and the gauge can never disagree.
    """
    try:
        latches = fold_latches(store)
        engaged = env_engaged(os.environ.get("PUMPGROK_KILLSWITCH"))
        return engaged or latches.kill_event == "KillSwitchSet"
    except Exception:
        return True


class LedgerUnavailable(Exception):
    """Ledger unwritable and the bounded buffer is full."""


@dataclass
class DegradedState:
    """AUTO-005 degraded-mode probes and behavior switches (paper-engine.md 6.7).

    Each field is a probe value that the behavior queries below read. The serve
    path does not feed ``llm_available`` or ``rpc_endpoints``; they are set at
    construction only.
    """

    #: LLM (x.ai) reachable; False degrades bot-08-signal to rule-based scoring.
    llm_available: bool = True
    #: RPC endpoints in failover order; False entries are down.
    rpc_endpoints: list[bool] = field(default_factory=lambda: [True])
    #: Ledger writable; False buffers orders up to LEDGER_BUFFER_CAP.
    ledger_writable: bool = True
    #: Buffered order rows while the ledger is unwritable, in order.
    ledger_buffer: list[dict[str, Any]] = field(default_factory=list)
    #: persistence_down escalation already raised for the current outage.
    persistence_raised: bool = False

    # -- LLM (paper-engine.md 6.7 row 1) ---------------------------------
    def signal_scoring_mode(self, *, replay: bool) -> str:
        """``llm`` | ``rule_fallback`` | ``replay``."""
        if replay:
            return "replay"
        return "llm" if self.llm_available else "rule_fallback"

    # -- RPC (paper-engine.md 6.7 row 2) ----------------------------------
    @property
    def rpc_blind(self) -> bool:
        """True after every failover endpoint fails."""
        return bool(self.rpc_endpoints) and not any(self.rpc_endpoints)

    # -- ledger (paper-engine.md 6.7 row: unwritable) ----------------------
    def buffer_order(self, row: Mapping[str, Any]) -> None:
        """Buffer one refused order; raises past the 1000-event bound."""
        if len(self.ledger_buffer) >= LEDGER_BUFFER_CAP:
            raise LedgerUnavailable("order buffer full (1000 events)")
        self.ledger_buffer.append(dict(row))

    def drain_buffer(self, store: LedgerStore) -> int:
        """Append buffered rows in order after recovery; returns count.

        A row leaves the buffer only once its append has landed, so a failed append keeps it.
        """
        count = 0
        while self.ledger_buffer:
            row = self.ledger_buffer[0]
            store.append(
                ts_utc=str(row["ts_utc"]),
                source=str(row["source"]),
                correlation_id=str(row["correlation_id"]),
                idempotency_key=str(row["idempotency_key"]),
                type=str(row["type"]),
                payload=row["payload"],
            )
            self.ledger_buffer.pop(0)
            count += 1
        self.persistence_raised = False
        return count
