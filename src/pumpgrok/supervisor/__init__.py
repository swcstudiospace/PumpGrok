"""Supervisor package: ten-seat autonomous paper loop (paper-engine.md 6).

Owns the supervised loop the desk runs under in paper mode: roster-order
scheduling, per-seat heartbeats, bounded restarts with observe-only latches,
health/readiness, graceful shutdown, and the AUTO-005 degraded-mode matrix.
The resume and autonomy CLI verbs live in ``cli.py`` (plan 04-07); this
package provides the scheduler, latch, and shutdown semantics they drive.

Every wait goes through the injected :class:`Clock`; no wall-clock sleeps,
``asyncio.sleep``, ``asyncio.timeout`` or ``asyncio.wait_for`` appear here
(the ``tests/safety/test_static_guards.py`` suite enforces it).
"""

from __future__ import annotations

from pumpgrok.supervisor.health import HealthServer, build_status, is_ok, write_health_json
from pumpgrok.supervisor.lifecycle import (
    cancel_and_wait,
    drain,
    install_signal_handlers,
    shutdown,
)
from pumpgrok.supervisor.scheduler import (
    SEAT_CADENCES,
    TICK_S,
    DegradedState,
    LedgerUnavailable,
    Supervisor,
    assert_no_skew,
    cycle_timeout_s,
    run_once_replay,
)
from pumpgrok.supervisor.seat_task import (
    CLOCK_SKEW_S,
    ClockSkew,
    ObserveOnly,
    RestartPolicy,
    SeatContext,
    SeatTask,
    append_escalation,
    relay_tail,
)

__all__ = [
    "CLOCK_SKEW_S",
    "SEAT_CADENCES",
    "TICK_S",
    "ClockSkew",
    "DegradedState",
    "HealthServer",
    "LedgerUnavailable",
    "ObserveOnly",
    "RestartPolicy",
    "SeatContext",
    "SeatTask",
    "Supervisor",
    "append_escalation",
    "assert_no_skew",
    "build_status",
    "cancel_and_wait",
    "cycle_timeout_s",
    "drain",
    "install_signal_handlers",
    "is_ok",
    "relay_tail",
    "run_once_replay",
    "shutdown",
    "write_health_json",
]
