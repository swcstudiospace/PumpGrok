"""Ten-seat supervised scheduler (paper-engine.md 6.1-6.2, 6.7).

Within one supervisor tick (``TICK_S = 1`` s) due seats start in roster order
(00..09). Each seat runs its cycle in its own ``asyncio.Task`` under
``clock.timeout(seat_timeout)``; a timed-out cycle counts as a crash. The serve
loop never awaits a cycle, so a slow seat cannot hold other seats or the next
tick, and a seat never overlaps itself. Every wait goes through the injected
clock.

AUTO-005 degraded modes live in :mod:`degraded`: LLM fallback,
RPC failover/BLIND, WS reconnect/DataStale, bounded unwritable-ledger
buffer, and clock-skew refusal. AUTO-006 is :func:`run_once_replay`: one
full ten-seat cycle over a fixture through the engine, risk, and paper
adapter, writing ``var/replay/<dataset>/ledger.sqlite`` with no network.
"""

from __future__ import annotations

from pumpgrok.supervisor.scheduler.degraded import (
    LEDGER_BUFFER_CAP,
    WS_STALE_S,
    DegradedState,
    LedgerUnavailable,
    assert_no_skew,
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

__all__ = [
    "DEFAULT_ROSTER_DIR",
    "EXIT_SEAT",
    "FIXTURE_SEAT_CADENCES",
    "LEDGER_BUFFER_CAP",
    "REPLAY_BUY_LAMPORTS",
    "REPLAY_SLIPPAGE_BPS",
    "REPLAY_TICKET",
    "RISK_ROW_TYPES",
    "ROSTER",
    "SEAT_CADENCES",
    "SERVE_PACE_S",
    "TICK_S",
    "TRADE_ROW_TYPES",
    "WS_STALE_S",
    "DegradedState",
    "LedgerUnavailable",
    "ReplayRuntime",
    "Supervisor",
    "assert_no_skew",
    "build_serve_replay",
    "cycle_timeout_s",
    "dataset_events_start",
    "dataset_stamps",
    "kill_switch_engaged",
    "open_replay_runtime",
    "rollover_key",
    "run_once_replay",
    "serve_fixture_timeline",
    "serve_replay",
]
