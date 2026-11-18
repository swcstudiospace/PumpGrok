"""Characterization: exit rules (STRUCT-003).

Pins ``engine/exits.py`` against the exit half of
``vendor/grokbot-pumpfun/tests/test_risk.py`` (vendor oracle, kept
byte-identical per R53).

Divergences from the oracle (deliberate):

- Thresholds come from the ``exits`` settings section, never from a risk
  budget; ``now`` is a required argument.
- Detail strings are English ASCII (``from entry``, ``from peak``; the
  vendor originals are Russian).
- A ``None`` price is no quote and holds; a zero price is a real quote
  (a drained curve) and is a full-loss stop-loss.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.engine.exits import EXIT_REASONS, apply_price, exit_signal
from pumpgrok.engine.models import PRICE_SCALE, ExitPosition

NOW = 1_700_000_000.0


def _px(value: float) -> int:
    """Test shorthand price to the integer ``PRICE_SCALE`` price (INT-01)."""
    return int((Decimal(str(value)) * PRICE_SCALE).to_integral_value(rounding=ROUND_HALF_UP))


def _lamports(sol: float) -> int:
    """Test shorthand SOL to integer lamports."""
    return int((Decimal(str(sol)) * 1_000_000_000).to_integral_value(rounding=ROUND_HALF_UP))


@pytest.fixture
def exits() -> ExitsSettings:
    return ExitsSettings(
        stop_loss_pct=30.0,
        take_profit_pct=120.0,
        trailing_stop_pct=35.0,
        max_hold_seconds=3600.0,
    )


def position(
    mint: str = "M",
    entry: float = 1.0,
    sol: float = 0.5,
    peak: float | None = None,
    opened_at: float = 0.0,
) -> ExitPosition:
    return ExitPosition(
        mint=mint,
        entry_price=_px(entry),
        sol_spent=_lamports(sol),
        opened_at=opened_at,
        peak_price=_px(entry) if peak is None else _px(peak),
    )


def test_exit_reason_order_is_documented() -> None:
    assert EXIT_REASONS == ("stop_loss", "take_profit", "trailing_stop", "max_hold")


def test_holds_while_nothing_triggered(exits: ExitsSettings) -> None:
    assert exit_signal(position(entry=1.0, opened_at=1000.0), _px(1.5), exits, now=1100.0) is None


def test_take_profit_fires(exits: ExitsSettings) -> None:
    signal = exit_signal(position(entry=1.0, opened_at=1000.0), _px(2.2), exits, now=1100.0)
    assert signal is not None and signal.reason == "take_profit"
    assert "+120" in signal.detail


def test_take_profit_boundary(exits: ExitsSettings) -> None:
    signal = exit_signal(position(entry=1.0), _px(2.2), exits, now=1.0)
    assert signal is not None and signal.reason == "take_profit"
    assert exit_signal(position(entry=1.0), _px(2.19), exits, now=1.0) is None


def test_stop_loss_wins_over_everything(exits: ExitsSettings) -> None:
    """A drawdown below the stop closes the position even after a peak."""
    signal = exit_signal(position(entry=1.0, peak=3.0, opened_at=0.0), _px(0.6), exits, now=1.0)
    assert signal is not None and signal.reason == "stop_loss"


def test_stop_loss_boundary(exits: ExitsSettings) -> None:
    pos = position(entry=1.0)
    signal = exit_signal(pos, _px(0.70), exits, now=1.0)
    assert signal is not None and signal.reason == "stop_loss"
    assert exit_signal(pos, _px(0.71), exits, now=1.0) is None


def test_trailing_stop_fires_after_peak(exits: ExitsSettings) -> None:
    pos = position(entry=1.0, peak=2.0, opened_at=1000.0)
    assert exit_signal(pos, _px(1.4), exits, now=1100.0) is None  # 30% drawdown
    signal = exit_signal(pos, _px(1.29), exits, now=1100.0)  # 35.5% drawdown
    assert signal is not None and signal.reason == "trailing_stop"
    assert "from peak" in signal.detail


def test_trailing_ignores_price_below_entry(exits: ExitsSettings) -> None:
    """Below entry the stop-loss owns the position, not the trailing stop."""
    signal = exit_signal(
        position(entry=1.0, peak=1.0, opened_at=1000.0), _px(0.8), exits, now=1100.0
    )
    assert signal is None


def test_trailing_uses_live_price_as_peak(exits: ExitsSettings) -> None:
    """Peak updates outside the pure check: the watcher writes it, so a spike
    up and back is not lost."""
    pos = position(entry=1.0, peak=1.0)
    assert exit_signal(pos, _px(2.19), exits, now=1.0) is None  # not take-profit yet
    assert pos.peak_price == _px(1.0)  # the function itself never writes
    pos.peak_price = _px(2.19)
    signal = exit_signal(pos, _px(1.4), exits, now=1.0)
    assert signal is not None and signal.reason == "trailing_stop"


def test_zero_disables_each_rule(exits: ExitsSettings) -> None:
    disabled = exits.model_copy(
        update={"take_profit_pct": 0.0, "trailing_stop_pct": 0.0, "max_hold_seconds": 0.0}
    )
    pos = position(entry=1.0, peak=5.0, opened_at=1000.0)
    assert exit_signal(pos, _px(4.0), disabled, now=10**9) is None
    signal = exit_signal(pos, _px(0.5), disabled, now=10**9)
    assert signal is not None and signal.reason == "stop_loss"


def test_max_hold_closes_stale_position(exits: ExitsSettings) -> None:
    pos = position(entry=1.0, opened_at=1000.0)
    signal = exit_signal(pos, _px(1.5), exits, now=1000.0 + 3600.0)
    assert signal is not None and signal.reason == "max_hold"


def test_max_hold_does_not_cut_a_runner(exits: ExitsSettings) -> None:
    """A position riding up closes on take-profit, not on the timer."""
    pos = position(entry=1.0, opened_at=1000.0)
    signal = exit_signal(pos, _px(2.5), exits, now=1000.0 + 7200.0)
    assert signal is not None and signal.reason == "take_profit"


def test_zero_price_is_full_loss_stop(exits: ExitsSettings) -> None:
    """A drained curve prices at zero: that is a real -100% stop, not no quote."""
    signal = exit_signal(position(entry=1.0, opened_at=1000.0), _px(0.0), exits, now=1100.0)
    assert signal is not None and signal.reason == "stop_loss"
    assert signal.detail == "-100.0% from entry"


def test_zero_price_stop_loss_beats_trailing_peak(exits: ExitsSettings) -> None:
    """Stop-loss keeps priority even when a peak above entry would also trail."""
    pos = position(entry=1.0, peak=3.0, opened_at=1000.0)
    signal = exit_signal(pos, _px(0.0), exits, now=1100.0)
    assert signal is not None and signal.reason == "stop_loss"


def test_zero_price_closes_through_apply_price(exits: ExitsSettings) -> None:
    pos = position(entry=1.0, peak=1.5, opened_at=1000.0)
    signal = apply_price(pos, _px(0.0), exits, now=1100.0)
    assert signal is not None and signal.reason == "stop_loss"
    assert pos.peak_price == _px(1.5)  # zero never lowers the peak


def test_none_price_holds(exits: ExitsSettings) -> None:
    """No quote: nothing to measure, so no rule fires, not even max_hold."""
    pos = position(entry=1.0, peak=3.0, opened_at=1000.0)
    assert exit_signal(pos, None, exits, now=1000.0 + 7200.0) is None


def test_none_price_leaves_peak_alone(exits: ExitsSettings) -> None:
    pos = position(entry=1.0, peak=1.5, opened_at=1000.0)
    assert apply_price(pos, None, exits, now=1100.0) is None
    assert pos.peak_price == _px(1.5)


def test_invalid_entry_holds(exits: ExitsSettings) -> None:
    """An entry of zero has no percent vs entry, so no rule can measure it."""
    assert exit_signal(position(entry=0.0), _px(1.0), exits, now=1.0) is None
    assert exit_signal(position(entry=0.0), _px(0.0), exits, now=1.0) is None
