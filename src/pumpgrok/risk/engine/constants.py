"""R34 step vocabulary and session constants shared by the risk engine."""

from __future__ import annotations

import re

from pumpgrok.core.adapter import EXIT_RULE_REASONS

STEP_IDS: tuple[str, ...] = (
    "ledger_inconsistent",
    "kill_switch",
    "halted",
    "breaker_open",
    "live_gate",
    "approval_missing",
    "approval_mismatch",
    "seat_may_trade",
    "max_trades_per_day",
    "max_open_positions",
    "already_open",
    "creator_already_open",
    "max_trade_fraction",
    "max_token_fraction",
    "daily_loss_halt",
    "drawdown_halt",
    "data_stale",
    "size_too_small",
    "below_liquidity_floor",
)

#: Steps an exit sell never evaluates (paper-engine.md 5.2 line 578).
EXIT_SKIP_STEPS: frozenset[str] = frozenset(
    {
        "kill_switch",
        "halted",
        "breaker_open",
        "max_trades_per_day",
        "max_open_positions",
        "already_open",
        "creator_already_open",
        "max_trade_fraction",
        "max_token_fraction",
        "daily_loss_halt",
        "drawdown_halt",
        "data_stale",
        "size_too_small",
        "below_liquidity_floor",
    }
)

#: Exit reasons that earn the skip above. Adapter-internal force-closes
#: (``graduated``, ``blind_flatten``) carry no order; they still name the
#: same vocabulary when they do flow through ``check``.
EXIT_SELL_REASONS: frozenset[str] = frozenset(
    {"exit_rule", "rug_alert", "kill_flatten", "blind_flatten", "graduated", *EXIT_RULE_REASONS}
)

#: The rule-named exit reasons (engine/exits.py). Each one names the rule an approval binds.
RULE_EXIT_REASONS: frozenset[str] = frozenset(EXIT_RULE_REASONS)

#: System-initiated risk exits mint their own approval in any autonomy mode.
SYSTEM_EXIT_REASONS: frozenset[str] = frozenset({"kill_flatten", "rug_alert"})

#: Seats allowed to send each side (upgrade-plan RISK-005, R34 step 8).
BUY_SEAT = "bot-04-sniper"
SELL_SEAT = "bot-06-exit"

#: Exact constitution bytes (rules/pumpgrok-team.mdc:34). The dash is U+2013;
#: chr() keeps this file ASCII (no literal or backslash-u escape).
FLOOR_HALTED_DAILY = "FLOOR HALTED " + chr(0x2013) + " DAILY LOSS LIMIT"

#: A RISK KILL verdict on a mint, recorded by the RISK seat as a ledger
#: ``JournalNote`` with ``note_kind == "verdict"`` and this text shape.
#: A killed mint refuses buys desk-wide for the session; sells still pass.
KILL_VERDICT_RE = re.compile(r"^RISK verdict=KILL mint=(?P<mint>\S+)(?:\s+reason=.*)?$")


_RECHECK_STEPS: frozenset[str] = frozenset(
    {
        "ledger_inconsistent",
        "kill_switch",
        "halted",
        "breaker_open",
        "max_open_positions",
        "already_open",
        "creator_already_open",
        "max_trade_fraction",
        "max_token_fraction",
        "daily_loss_halt",
        "drawdown_halt",
        "data_stale",
        "size_too_small",
        "below_liquidity_floor",
    }
)


#: Decision-cache cap: generation-keyed entries, oldest evicted past this.
_DECISION_CACHE_MAX = 1024
