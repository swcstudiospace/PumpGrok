"""RiskEngine: the only component that may say no to an order (paper-engine.md 5.2, R24).

Library code, called in-process by ``PaperAdapter.place`` for every order
regardless of the RISK seat's health. Only ``RiskEngine`` appends ``HaltSet``
and ``BreakerTripped`` rows. Decisions bind ``order_hash``: the adapter must
refuse to proceed without a passed ``RiskDecision`` whose hash matches.

The 19 R34 steps run in exact order with first-failure-wins. Steps 13 and 14
cap rather than reject. A degraded reputation book (R62) refuses buys with the
breaker-scope reason ``reputation_degraded`` plus one Escalation per UTC day;
sells are not new entries, so exits and kill-flatten still run. Sells carrying
an exit reason in ``EXIT_SELL_REASONS`` skip steps 2-4 and 9-19 (reducing risk
is always allowed); every other order evaluates every step, so a manual sell is
still refused by an active kill switch, halt or open breaker. Steps 10-12 are
buy-only. Steps 13, 14, 18 and 19 compare lamport sizes, so sells auto-pass
them; steps 9, 15, 16 and 17 evaluate for sells too (trade counting, halt
detection and mark freshness are side-independent).

Approval consumption plus ``OrderPlaced`` in one transaction (TOOL-004) lands
in plan 04-07; here ``check`` returns the bound ``RiskDecision`` (with the
minted autonomous approval, when applicable) that the adapter consumes.
"""

from pumpgrok.risk.engine.constants import (
    _DECISION_CACHE_MAX,
    BUY_SEAT,
    EXIT_SELL_REASONS,
    EXIT_SKIP_STEPS,
    FLOOR_HALTED_DAILY,
    RULE_EXIT_REASONS,
    SELL_SEAT,
    STEP_IDS,
    SYSTEM_EXIT_REASONS,
)
from pumpgrok.risk.engine.core import RiskEngine
from pumpgrok.risk.engine.model import RiskDecision, halt_key, order_hash_for, utc_day

__all__ = [
    "BUY_SEAT",
    "EXIT_SELL_REASONS",
    "EXIT_SKIP_STEPS",
    "FLOOR_HALTED_DAILY",
    "RULE_EXIT_REASONS",
    "SELL_SEAT",
    "STEP_IDS",
    "SYSTEM_EXIT_REASONS",
    "RiskDecision",
    "RiskEngine",
    "halt_key",
    "order_hash_for",
    "utc_day",
]
