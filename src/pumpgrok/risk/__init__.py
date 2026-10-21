"""Risk engine pieces: 19-step check, limits, lamport sizing, R34 mapping.

Ported from ``vendor/grokbot-pumpfun/src/risk.py`` (oracle, kept
byte-identical per R53). The check engine (``risk/engine.py``) owns every
``HaltSet`` and ``BreakerTripped`` append (R24); the characterization suite
pins the vendor vocabulary it replaced.
"""

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
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.risk.sizing import (
    LAMPORTS_PER_SOL,
    MAX_SHARE_OF_REMAINING_BUDGET,
    MIN_TRADE_LAMPORTS,
    VENDOR_REASON_TO_R34,
    position_size_lamports,
    to_r34_reason,
)

__all__ = [
    "BUY_SEAT",
    "EXIT_SELL_REASONS",
    "EXIT_SKIP_STEPS",
    "FLOOR_HALTED_DAILY",
    "LAMPORTS_PER_SOL",
    "MAX_SHARE_OF_REMAINING_BUDGET",
    "MIN_TRADE_LAMPORTS",
    "SELL_SEAT",
    "STEP_IDS",
    "VENDOR_REASON_TO_R34",
    "EngineLimits",
    "RiskDecision",
    "RiskEngine",
    "halt_key",
    "order_hash_for",
    "position_size_lamports",
    "to_r34_reason",
]
