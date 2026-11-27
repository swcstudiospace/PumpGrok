"""Ten-seat supervised scheduler (paper-engine.md 6.1-6.2, 6.7).

Within one supervisor tick (``TICK_S = 1`` s) due seats start in roster order
(00..09). Each seat runs its cycle in its own ``asyncio.Task`` under
``clock.timeout(seat_timeout)``; a timed-out cycle counts as a crash. The serve
loop never awaits a cycle, so a slow seat cannot hold other seats or the next
tick, and a seat never overlaps itself. Every wait goes through the injected
clock.

AUTO-005 degraded modes live in :mod:`degraded`: LLM fallback, the bounded
unwritable-ledger buffer, and the health latches folded from the ledger.
AUTO-006 is :func:`run_once_replay`: one full ten-seat cycle over a fixture
through the engine, risk, and paper adapter, writing
``var/replay/<dataset>/ledger.sqlite`` with no network.
"""

from __future__ import annotations

from pumpgrok.supervisor.scheduler.degraded import (
    LEDGER_BUFFER_CAP,
    DegradedState,
    LedgerUnavailable,
    assert_no_skew,
    fold_latches,
    kill_switch_engaged,
)
from pumpgrok.supervisor.scheduler.replay_runtime import (
    DEFAULT_ROSTER_DIR,
    EXIT_SEAT,
    FIXTURE_SEAT_CADENCES,
    REPLAY_BUY_LAMPORTS,
    REPLAY_SLIPPAGE_BPS,
    REPLAY_TICKET,
    RISK_ROW_TYPES,
    SERVE_PACE_S,
    TRADE_ROW_TYPES,
    ReplayRuntime,
    dataset_events_start,
    dataset_stamps,
    open_replay_runtime,
)
from pumpgrok.supervisor.scheduler.serve import (
    build_serve_replay,
    run_once_replay,
    serve_fixture_timeline,
    serve_replay,
)
from pumpgrok.supervisor.scheduler.supervisor import (
    ROSTER,
    SEAT_CADENCES,
    TICK_S,
    Supervisor,
    cycle_timeout_s,
    rollover_key,
)
from pumpgrok.supervisor.scheduler.wake import (
    ALLOWED_TIMERS,
    EVENT_TIMERS,
    SEAT_WAKES,
    UnknownTimerError,
    assert_allowed_timers,
    dispatch,
    wake_order,
    wakes_for,
)

__all__ = [
    "ALLOWED_TIMERS",
    "DEFAULT_ROSTER_DIR",
    "EVENT_TIMERS",
    "EXIT_SEAT",
    "FIXTURE_SEAT_CADENCES",
    "LEDGER_BUFFER_CAP",
    "REPLAY_BUY_LAMPORTS",
    "REPLAY_SLIPPAGE_BPS",
    "REPLAY_TICKET",
    "RISK_ROW_TYPES",
    "ROSTER",
    "SEAT_CADENCES",
    "SEAT_WAKES",
    "SERVE_PACE_S",
    "TICK_S",
    "TRADE_ROW_TYPES",
    "DegradedState",
    "LedgerUnavailable",
    "ReplayRuntime",
    "Supervisor",
    "UnknownTimerError",
    "assert_allowed_timers",
    "assert_no_skew",
    "build_serve_replay",
    "cycle_timeout_s",
    "dataset_events_start",
    "dataset_stamps",
    "dispatch",
    "fold_latches",
    "kill_switch_engaged",
    "open_replay_runtime",
    "rollover_key",
    "run_once_replay",
    "serve_fixture_timeline",
    "serve_replay",
    "wake_order",
    "wakes_for",
]
