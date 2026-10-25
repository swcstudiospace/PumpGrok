"""Degraded-mode probes and behavior switches (paper-engine.md 6.7)."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pumpgrok.core.ids import Clock
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.risk.killswitch import env_engaged
from pumpgrok.supervisor.seat_task import CLOCK_SKEW_S, ClockSkew

log = logging.getLogger("pumpgrok.supervisor.scheduler")

#: WS silence budget before DataStale trips (paper-engine.md 6.7).
WS_STALE_S = 120.0
#: Bounded buffer for orders while the ledger is unwritable (paper-engine.md 6.7).
LEDGER_BUFFER_CAP = 1000


def kill_switch_engaged(store: LedgerStore) -> bool:
    """Shared kill-switch latch for the health body and the metrics gauge.

    True when a ``KillSwitchSet`` row has no later ``KillSwitchCleared``, or
    when ``PUMPGROK_KILLSWITCH`` engages in this process (fail-closed, same
    fold as ``run_halt_status``). File and alert-command sources are enforced
    at decision time by the risk engine; unreadable ledgers report engaged
    rather than all-clear. ``health_status`` and the serve ``_snapshot`` both
    read this so the body and the gauge can never disagree.
    """
    try:
        engaged = env_engaged(os.environ.get("PUMPGROK_KILLSWITCH"))
        for event in store.read(limit=None):
            event_type = event.get("type")
            if event_type == "KillSwitchSet":
                engaged = True
            elif event_type == "KillSwitchCleared":
                engaged = env_engaged(os.environ.get("PUMPGROK_KILLSWITCH"))
        return engaged
    except Exception:
        return True


class LedgerUnavailable(Exception):
    """Ledger unwritable and the bounded buffer is full."""


def assert_no_skew(store: LedgerStore, clock: Clock) -> None:
    """Refuse appends when the clock trails the ledger head beyond 5 s."""
    events = store.read(limit=None)
    if not events:
        return
    head_ts = parse_ts_utc(str(events[-1].get("ts_utc", "")))
    if DegradedState.skew_detected(clock.now(), head_ts):
        raise ClockSkew(f"clock trails ledger head by over {CLOCK_SKEW_S:.0f}s")


@dataclass
class DegradedState:
    """AUTO-005 degraded-mode probes and behavior switches (paper-engine.md 6.7).

    Every field has a setter (the seat cycles feed observations) and a
    behavior query (the scheduler and health consult it). Recovery is the
    same setter with the healthy value; each row below is asserted with its
    recovery in ``tests/supervisor/test_degraded.py``.
    """

    #: LLM (x.ai) reachable; False degrades bot-08-signal.
    llm_available: bool = True
    #: signal.require_llm: when True the desk is observe-only for new buys
    #: while the LLM is down; otherwise rule-based scoring in live-paper.
    require_llm: bool = False
    #: RPC endpoints in failover order; False entries are down.
    rpc_endpoints: list[bool] = field(default_factory=lambda: [True])
    #: PumpPortal WS last frame (virtual ts), None when never connected.
    ws_last_frame_at: float | None = None
    #: Ledger writable; False buffers orders up to LEDGER_BUFFER_CAP.
    ledger_writable: bool = True
    #: Buffered order rows while the ledger is unwritable, in order.
    ledger_buffer: list[dict[str, Any]] = field(default_factory=list)
    #: persistence_down escalation already raised for the current outage.
    persistence_raised: bool = False

    # -- LLM (paper-engine.md 6.7 row 1) ---------------------------------
    def signal_scoring_mode(self, *, replay: bool) -> str:
        """``llm`` | ``rule_fallback`` | ``observe_only_buys`` | ``replay``."""
        if replay:
            return "replay"
        if self.llm_available:
            return "llm"
        if self.require_llm:
            return "observe_only_buys"
        return "rule_fallback"

    # -- RPC (paper-engine.md 6.7 row 2) ----------------------------------
    @property
    def rpc_blind(self) -> bool:
        """True after every failover endpoint fails."""
        return bool(self.rpc_endpoints) and not any(self.rpc_endpoints)

    def note_rpc_result(self, index: int, ok: bool) -> None:
        """Record one endpoint probe; healthy probes recover BLIND."""
        if 0 <= index < len(self.rpc_endpoints):
            self.rpc_endpoints[index] = ok

    # -- WS (paper-engine.md 6.7 rows 3-4) --------------------------------
    def note_ws_frame(self, at: float) -> None:
        """Fresh PumpPortal frame; recovers DataStale."""
        self.ws_last_frame_at = at

    def ws_data_stale(self, now: float) -> bool:
        """DataStale trips after 120 s of WS silence."""
        if self.ws_last_frame_at is None:
            return False
        return now - self.ws_last_frame_at > WS_STALE_S

    # -- ledger (paper-engine.md 6.7 row: unwritable) ----------------------
    def buffer_order(self, row: Mapping[str, Any]) -> None:
        """Buffer one refused order; raises past the 1000-event bound."""
        if len(self.ledger_buffer) >= LEDGER_BUFFER_CAP:
            raise LedgerUnavailable("order buffer full (1000 events)")
        self.ledger_buffer.append(dict(row))

    def drain_buffer(self, store: LedgerStore) -> int:
        """Append buffered rows in order after recovery; returns count."""
        count = 0
        while self.ledger_buffer:
            row = self.ledger_buffer.pop(0)
            store.append(
                ts_utc=str(row["ts_utc"]),
                source=str(row["source"]),
                correlation_id=str(row["correlation_id"]),
                idempotency_key=str(row["idempotency_key"]),
                type=str(row["type"]),
                payload=row["payload"],
            )
            count += 1
        self.persistence_raised = False
        return count

    # -- clock skew (paper-engine.md 6.7 row: skew) -------------------------
    @staticmethod
    def skew_detected(now: float, head_ts: float) -> bool:
        """True when the clock trails the ledger head beyond 5 s."""
        return now < head_ts - CLOCK_SKEW_S
