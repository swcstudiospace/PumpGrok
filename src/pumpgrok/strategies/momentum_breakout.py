"""momentum_breakout: buy a break above the recent window high; exit on a stop or a hold cap.

PENDING OWNER APPROVAL. DEFAULTS are starting proposals with reasons in 15-PLANS-INDEX.md,
not final pins (owner decision 2).

Rule, as proposed:
- Over the last lookback_seconds, counting prior ticks of the same mint, window_high is the
  highest price seen.
- BUY when price >= window_high * (1 + breakout_pct / 100) and no position is open in the mint.
- SELL when price <= entry_price * (1 - stop_loss_pct / 100), or when the position is at least
  max_hold_seconds old. The stop is checked first.

Prices are integer lamports. Percent parameters are read as exact rationals, so a value equal to
its bound triggers and one step beyond it does not.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from pumpgrok.strategies.base import Intent, Side, StrategyContext
from pumpgrok.strategies.recovery import Position, StrategyBook, exact
from pumpgrok.upgrade.bounds import KeyBound

__all__ = ["ENTRY_LAMPORTS", "MomentumBreakout"]

#: Size of each entry, equal to the replay buy amount (supervisor REPLAY_BUY_LAMPORTS).
ENTRY_LAMPORTS = 10_000_000


class MomentumBreakout:
    """The breakout strategy: a buy above the window high, a sell on stop or hold cap."""

    strategy_id: ClassVar[str] = "momentum_breakout"
    BOUNDS: ClassVar[Mapping[str, KeyBound]] = {
        "lookback_seconds": KeyBound(minimum=60, maximum=1800),
        "breakout_pct": KeyBound(minimum=1.0, maximum=200.0),
        "max_hold_seconds": KeyBound(minimum=60, maximum=3600),
        "stop_loss_pct": KeyBound(minimum=1.0, maximum=100.0),
    }
    DEFAULTS: ClassVar[Mapping[str, Any]] = {
        "lookback_seconds": 300,
        "breakout_pct": 20.0,
        "max_hold_seconds": 900,
        "stop_loss_pct": 25.0,
    }

    def __init__(self) -> None:
        self.book = StrategyBook.fresh()

    def on_tick(self, context: StrategyContext) -> tuple[Intent, ...]:
        tick = context.tick
        book = self.book
        held = book.positions.get(tick.mint)
        intents: list[Intent] = []
        if held is None:
            window = book.window(tick.mint, tick.ts, float(self.DEFAULTS["lookback_seconds"]))
            if window:
                high = max(point.price_lamports for point in window)
                threshold = exact(high) * (1 + exact(self.DEFAULTS["breakout_pct"]) / 100)
                if exact(tick.price_lamports) >= threshold:
                    book.open(
                        tick.mint,
                        Position(
                            entry_ts=tick.ts,
                            entry_price_lamports=tick.price_lamports,
                            size_lamports=ENTRY_LAMPORTS,
                        ),
                    )
                    reason = f"breakout over window high {high}"
                    intents.append(_intent(context, "buy", ENTRY_LAMPORTS, reason))
        else:
            stop_pct = exact(self.DEFAULTS["stop_loss_pct"])
            stop = exact(held.entry_price_lamports) * (1 - stop_pct / 100)
            reason = ""
            if exact(tick.price_lamports) <= stop:
                reason = "stop_loss"
            elif tick.ts - held.entry_ts >= self.DEFAULTS["max_hold_seconds"]:
                reason = "max_hold"
            if reason:
                book.close(tick.mint)
                intents.append(_intent(context, "sell", held.size_lamports, reason))
        book.observe(tick.mint, tick.ts, tick.price_lamports)
        return tuple(intents)


def _intent(context: StrategyContext, side: Side, size_lamports: int, reason: str) -> Intent:
    mint = context.tick.mint
    return Intent(
        strategy_id=MomentumBreakout.strategy_id,
        mint=mint,
        side=side,
        size_lamports=size_lamports,
        decision_id=f"{MomentumBreakout.strategy_id}:{side}:{mint}:{context.tick.ts!r}",
        reason=reason,
        version_id=context.version_id,
    )
