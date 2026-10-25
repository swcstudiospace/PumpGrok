"""Risk engine pieces: 19-step check, limits, lamport sizing, R34 mapping.

Ported from the retired oracle ``src/risk.py`` (pin 409e74c,
byte-identical per R53). The check engine (``risk/engine.py``) owns every
``HaltSet`` and ``BreakerTripped`` append (R24); the characterization suite
pins the vendor vocabulary it replaced.
"""

from pumpgrok.risk.breakers import (
    BREAKER_NAMES,
    Breaker,
    BreakerSet,
    DataStaleBreaker,
    ExecErrorsBreaker,
    LossVelocityBreaker,
    breaker_reset_key,
    breaker_trip_key,
)
from pumpgrok.risk.engine import (
    BUY_SEAT,
    EXIT_SELL_REASONS,
    EXIT_SKIP_STEPS,
    FLOOR_HALTED_DAILY,
    SELL_SEAT,
    STEP_IDS,
    RiskDecision,
    RiskEngine,
    halt_key,
    order_hash_for,
)
from pumpgrok.risk.killswitch import (
    SEAT_RE,
    FlattenOrder,
    InflightBarrier,
    KillState,
    KillSwitch,
    kill_file_text,
    kill_switch_key,
    parse_kill_line,
)
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.risk.sizing import (
    MAX_SHARE_OF_REMAINING_BUDGET,
    MIN_TRADE_LAMPORTS,
    VENDOR_REASON_TO_R34,
    position_size_lamports,
    to_r34_reason,
)

__all__ = [
    "BREAKER_NAMES",
    "BUY_SEAT",
    "EXIT_SELL_REASONS",
    "EXIT_SKIP_STEPS",
    "FLOOR_HALTED_DAILY",
    "MAX_SHARE_OF_REMAINING_BUDGET",
    "MIN_TRADE_LAMPORTS",
    "SEAT_RE",
    "SELL_SEAT",
    "STEP_IDS",
    "VENDOR_REASON_TO_R34",
    "Breaker",
    "BreakerSet",
    "DataStaleBreaker",
    "EngineLimits",
    "ExecErrorsBreaker",
    "FlattenOrder",
    "InflightBarrier",
    "KillState",
    "KillSwitch",
    "LossVelocityBreaker",
    "RiskDecision",
    "RiskEngine",
    "breaker_reset_key",
    "breaker_trip_key",
    "halt_key",
    "kill_file_text",
    "kill_switch_key",
    "order_hash_for",
    "parse_kill_line",
    "position_size_lamports",
    "to_r34_reason",
]
