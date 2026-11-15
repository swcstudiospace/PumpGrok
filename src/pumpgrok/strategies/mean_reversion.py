"""mean_reversion: buy a price well below its recent mean; exit at the mean, a stop or a hold cap.

PENDING OWNER APPROVAL. DEFAULTS are starting proposals with reasons in 15-PLANS-INDEX.md,
not final pins (owner decision 2).

Rule, as proposed:
- Over the last window_seconds, counting prior ticks of the same mint, take the population mean
  and standard deviation of the prices. Fewer than two points, or zero variance, decides nothing.
- BUY when price <= mean - z_threshold * stddev and no position is open in the mint.
- SELL when price <= entry_price * (1 - stop_loss_pct / 100), or when the position is at least
  max_hold_seconds old, or when price >= mean. The stop is checked first, then the hold cap, then
  the mean.

Prices are integer lamports. The entry test is exact: mean - price >= z * stddev is squared on both
sides, so it is rational arithmetic with no square root and no float comparison.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Any, ClassVar

from pumpgrok.strategies.base import Intent, Side, StrategyContext, TapePoint
from pumpgrok.strategies.recovery import Position, StrategyBook, exact
from pumpgrok.upgrade.bounds import KeyBound

__all__ = ["ENTRY_LAMPORTS", "MeanReversion"]

#: Size of each entry, equal to the replay buy amount (supervisor REPLAY_BUY_LAMPORTS).
ENTRY_LAMPORTS = 10_000_000


def _stats(window: Sequence[TapePoint]) -> tuple[Fraction, Fraction] | None:
    """Exact population mean and variance of the window, or None when they decide nothing."""
    count = len(window)
    if count < 2:
        return None
    total = sum(point.price_lamports for point in window)
    squares = sum(point.price_lamports * point.price_lamports for point in window)
    mean = Fraction(total, count)
    variance = Fraction(squares, count) - mean * mean
    if variance == 0:
        return None
    return mean, variance


class MeanReversion:
    """The reversion strategy: a buy far below the mean, a sell back at the mean or on stop."""

    strategy_id: ClassVar[str] = "mean_reversion"
    BOUNDS: ClassVar[Mapping[str, KeyBound]] = {
        "window_seconds": KeyBound(minimum=60, maximum=7200),
        "z_threshold": KeyBound(minimum=0.5, maximum=5.0),
        "max_hold_seconds": KeyBound(minimum=60, maximum=3600),
        "stop_loss_pct": KeyBound(minimum=1.0, maximum=100.0),
    }
    DEFAULTS: ClassVar[Mapping[str, Any]] = {
        "window_seconds": 600,
        "z_threshold": 2.0,
        "max_hold_seconds": 900,
        "stop_loss_pct": 15.0,
    }

    def __init__(self) -> None:
        self.book = StrategyBook.fresh()

    def on_tick(self, context: StrategyContext) -> tuple[Intent, ...]:
        tick = context.tick
        book = self.book
        held = book.positions.get(tick.mint)
        window = book.window(tick.mint, tick.ts, float(self.DEFAULTS["window_seconds"]))
        stats = _stats(window)
        intents: list[Intent] = []
        if held is None:
            if stats is not None:
                mean, variance = stats
                gap = mean - tick.price_lamports
                z = exact(self.DEFAULTS["z_threshold"])
                if gap >= 0 and gap * gap >= z * z * variance:
                    book.open(
                        tick.mint,
                        Position(
                            entry_ts=tick.ts,
                            entry_price_lamports=tick.price_lamports,
                            size_lamports=ENTRY_LAMPORTS,
                        ),
                    )
                    reason = f"price {tick.price_lamports} at least z sigma below window mean"
                    intents.append(_intent(context, "buy", ENTRY_LAMPORTS, reason))
        else:
            stop_pct = exact(self.DEFAULTS["stop_loss_pct"])
            stop = exact(held.entry_price_lamports) * (1 - stop_pct / 100)
            reason = ""
            if exact(tick.price_lamports) <= stop:
                reason = "stop_loss"
            elif tick.ts - held.entry_ts >= self.DEFAULTS["max_hold_seconds"]:
                reason = "max_hold"
            elif stats is not None and exact(tick.price_lamports) >= stats[0]:
                reason = "mean_reached"
            if reason:
                book.close(tick.mint)
                intents.append(_intent(context, "sell", held.size_lamports, reason))
        book.observe(tick.mint, tick.ts, tick.price_lamports)
        return tuple(intents)


def _intent(context: StrategyContext, side: Side, size_lamports: int, reason: str) -> Intent:
    mint = context.tick.mint
    return Intent(
        strategy_id=MeanReversion.strategy_id,
        mint=mint,
        side=side,
        size_lamports=size_lamports,
        decision_id=f"{MeanReversion.strategy_id}:{side}:{mint}:{context.tick.ts!r}",
        reason=reason,
        version_id=context.version_id,
    )
