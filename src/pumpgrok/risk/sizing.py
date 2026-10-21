"""Lamport position sizer with vendor-identical constants.

Port of the ``position_size`` half of ``vendor/grokbot-pumpfun/src/risk.py``.
All prose is English; the vendor text is Russian.

Deliberate divergences from the oracle:

- Money is integer lamports, never ``float`` SOL (R28/R29). The vendor
  computes ``round(min(by_score, by_budget), 6)`` in SOL; the port rounds to
  the nearest lamport, which is strictly more precise. Pinned values below
  are exact in both units so the characterization cannot tell the difference.
- Score is clamped to ``0..1`` exactly like the vendor
  (``max(0.0, min(1.0, score))``); scores above 1.0 never inflate the stake.
- The vendor ``evaluate`` reason strings carry free-text details
  (``"daily_loss_limit_hit (2.0000 SOL)"``). The R34 vocabulary (paper-engine
  5.2, CONTEXT R23) uses fixed ids, so this module maps the vendor prefix to
  the R34 id via :data:`VENDOR_REASON_TO_R34`. Only ``daily_loss_limit_hit``
  changes (to ``daily_loss_halt``); every other code is already the R34 id.
- Day-rollover auto-clear is not ported (R5). ``evaluate`` callers must
  refuse orders while halted until a human clears the halt; UTC rollover
  never clears anything.

Vendor reason to R34 mapping (also recorded in the test docstring):

=========================  =================
vendor ``evaluate``        R34 id
=========================  =================
``daily_loss_limit_hit``   ``daily_loss_halt``
``max_trades_per_day``     ``max_trades_per_day``
``max_open_positions``     ``max_open_positions``
``already_open``           ``already_open``
``size_too_small``         ``size_too_small``
``ok``                     ``ok``
=========================  =================
"""

from __future__ import annotations

LAMPORTS_PER_SOL = 1_000_000_000

# Below this size a trade makes no sense: fees and tips would eat it.
# Vendor MIN_TRADE_SOL = 0.01 (risk.py:36).
MIN_TRADE_LAMPORTS = 10_000_000

# Share of the remaining daily-loss budget risked on one trade.
# Vendor-identical (risk.py:33).
MAX_SHARE_OF_REMAINING_BUDGET = 0.30

# Vendor ``RiskManager.evaluate`` reason prefix to R34 id (paper-engine 5.2).
# Unknown prefixes raise in :func:`to_r34_reason`: an unmapped reason is a
# drifted vocabulary, never a pass.
VENDOR_REASON_TO_R34: dict[str, str] = {
    "daily_loss_limit_hit": "daily_loss_halt",
    "max_trades_per_day": "max_trades_per_day",
    "max_open_positions": "max_open_positions",
    "already_open": "already_open",
    "size_too_small": "size_too_small",
    "ok": "ok",
}


def position_size_lamports(
    score: float,
    *,
    max_trade_lamports: int,
    remaining_budget_lamports: int,
) -> int:
    """Size a position in lamports: proportional to score, capped twice.

    ``by_score`` scales the per-trade ceiling by the clamped score;
    ``by_budget`` takes at most 30 percent of what is left of the daily-loss
    budget. The smaller wins, exactly like the vendor formula.
    """
    clamped = max(0.0, min(1.0, score))
    by_score = max_trade_lamports * clamped
    by_budget = remaining_budget_lamports * MAX_SHARE_OF_REMAINING_BUDGET
    return round(min(by_score, by_budget))


def to_r34_reason(vendor_reason: str) -> str:
    """Map a vendor ``evaluate`` reason (with optional detail) to its R34 id.

    ``"daily_loss_limit_hit (2.0000 SOL)"`` becomes ``"daily_loss_halt"``;
    bare codes pass through unchanged. Raises :class:`ValueError` on an
    unknown prefix so vocabulary drift fails loudly.
    """
    code = vendor_reason.split("(", 1)[0].strip()
    try:
        return VENDOR_REASON_TO_R34[code]
    except KeyError:
        raise ValueError(f"unknown vendor evaluate reason: {vendor_reason!r}") from None
