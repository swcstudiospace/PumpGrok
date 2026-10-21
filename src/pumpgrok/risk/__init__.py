"""Risk engine pieces: lamport-first sizing and R34 reason mapping.

Ported from ``vendor/grokbot-pumpfun/src/risk.py`` (oracle, kept
byte-identical per R53). The full check engine (halts, breakers, limits)
lands in ``risk/engine.py`` in plan 04-05; this package holds only the
pieces the characterization suite pins first.
"""

from pumpgrok.risk.sizing import (
    LAMPORTS_PER_SOL,
    MAX_SHARE_OF_REMAINING_BUDGET,
    MIN_TRADE_LAMPORTS,
    VENDOR_REASON_TO_R34,
    position_size_lamports,
    to_r34_reason,
)

__all__ = [
    "LAMPORTS_PER_SOL",
    "MAX_SHARE_OF_REMAINING_BUDGET",
    "MIN_TRADE_LAMPORTS",
    "VENDOR_REASON_TO_R34",
    "position_size_lamports",
    "to_r34_reason",
]
