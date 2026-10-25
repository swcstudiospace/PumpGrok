"""Position exit rules: stop-loss first, then profit, then time.

Port of the exit half of the retired oracle ``src/risk.py``. All prose
is English; the vendor text is Russian.

Deliberate divergences from the oracle:

- The rule order is the priority order: first save the money, then take
  the profit, then guard the profit, and only then close on time. A
  position riding up must never be cut by the timer.
- ``exit_signal`` takes ``now`` as a required argument. ``now or
  time.time()`` defaults are banned: ``0.0`` is falsy and would silently
  become wall time.
- Thresholds come from the ``exits`` settings section, never from
  ``core/risk_budget.py`` (R20 schema stays untouched).
- Day-rollover auto-clear is not ported (R5).
- Detail strings are English ASCII (``from entry``, ``from peak``).
"""

from decimal import Decimal, ROUND_HALF_UP

from pydantic import BaseModel, ConfigDict

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.engine.models import PRICE_SCALE, ExitPosition

# Rule order is priority order. Stop-loss first, profit second, trailing
# third, time last: a runner closes on take-profit, not on the timer.
EXIT_REASONS = ("stop_loss", "take_profit", "trailing_stop", "max_hold")


class ExitSignal(BaseModel):
    """Why to close a position, and what justifies it."""

    model_config = ConfigDict(frozen=True)

    reason: str
    detail: str = ""


def pnl_pct(position: ExitPosition, price: int) -> float:
    """PnL percent vs entry. Prices are PRICE_SCALE integers; the percent is a ratio."""
    if position.entry_price <= 0:
        return 0.0
    return (price - position.entry_price) / position.entry_price * 100.0


def stop_loss_triggered(position: ExitPosition, price: int, stop_loss_pct: float) -> bool:
    if position.entry_price <= 0 or price <= 0 or stop_loss_pct <= 0:
        return False
    return -pnl_pct(position, price) >= stop_loss_pct


def exit_signal(
    position: ExitPosition,
    price: int,
    cfg: ExitsSettings,
    now: float,
) -> ExitSignal | None:
    """Whether to exit and why. None means hold.

    Stop-loss is only one of four rules here. Without the rest, a
    position that tripled would have no way to close green: it would
    just wait to slide back to the stop.
    """
    if price <= 0 or position.entry_price <= 0:
        return None

    change = pnl_pct(position, price)

    if cfg.stop_loss_pct and -change >= cfg.stop_loss_pct:
        return ExitSignal(reason="stop_loss", detail=f"{change:+.1f}% from entry")

    if cfg.take_profit_pct and change >= cfg.take_profit_pct:
        return ExitSignal(reason="take_profit", detail=f"{change:+.1f}% from entry")

    # Trailing only works above entry: below it the stop-loss owns the
    # drawdown, otherwise both rules would fight over the same slide.
    peak = max(position.peak_price, price)
    if cfg.trailing_stop_pct and peak > position.entry_price:
        drawdown = (peak - price) / peak * 100.0
        if drawdown >= cfg.trailing_stop_pct:
            return ExitSignal(
                reason="trailing_stop",
                detail=f"drawdown {drawdown:.1f}% from peak {pnl_pct(position, peak):+.1f}%",
            )

    if cfg.max_hold_seconds and position.opened_at:
        held = now - position.opened_at
        if held >= cfg.max_hold_seconds:
            return ExitSignal(
                reason="max_hold",
                detail=f"{held / 60:.0f} min in position, {change:+.1f}%",
            )

    return None


def apply_price(
    position: ExitPosition,
    price: int,
    cfg: ExitsSettings,
    now: float,
) -> ExitSignal | None:
    """Ratchet the trailing-stop peak, then evaluate. Single entry point.

    ``exit_signal`` stays pure (it never writes ``peak_price``), so every
    caller that only calls it must replicate the ratchet or the trailing
    stop never advances. Call this instead: the mutation is the contract,
    and the watcher routes through here so the invariant lives in one
    place instead of two modules.
    """
    position.peak_price = max(position.peak_price, price)
    return exit_signal(position, price, cfg, now)


def restore_peak(entry_price: int, ledger_peak: Decimal) -> int:
    """Peak to track after a restart, from the ledger fold. Pure.

    The serve loop writes the running peak into each ``MarkToMarket`` row's
    ``spot`` (the reducer ratchets ``price_peak`` from it, existing R32 type,
    no new event), so a fresh book re-learns the peak from the fold instead
    of from the next curve read. Never below entry: a position that never
    printed above entry restarts with the entry peak. Conversion matches
    ``_scaled_price`` (half-up); an undecodable peak raises instead of
    silently defaulting.
    """
    scaled = int((ledger_peak * PRICE_SCALE).to_integral_value(rounding=ROUND_HALF_UP))
    return max(entry_price, scaled)
