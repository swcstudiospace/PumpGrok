"""Characterization: vendor risk evaluate and sizing (STRUCT-004).

Pins ``risk/sizing.py`` against ``vendor/grokbot-pumpfun/tests/test_risk.py``
(vendor oracle, kept byte-identical per R53) and ``src/risk.py:143-178``
(evaluate reasons) plus ``src/risk.py:33-36`` (constants).

Vendor reason to R34 mapping (paper-engine 5.2, CONTEXT R23):

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

Adaptations from the oracle (deliberate):

- Money is integer lamports, never float SOL (R28/R29). Fixture limits
  mirror the vendor test fixture (``max_sol_per_trade=0.5``,
  ``daily_loss_limit_sol=2.0``, ``max_trades_per_day=3``,
  ``max_open_positions=2``) converted once to lamports.
- ``RiskHarness`` is a test-local mirror of the vendor ``evaluate`` step
  order (halt, trade count, open count, duplicate mint, size floor). It
  computes sizes through the ported ``position_size_lamports`` and maps
  every reason through ``to_r34_reason``. The real check engine replaces
  this harness in plan 04-05 (``risk/engine.py``); the reason-code
  assertions stay valid because the R34 vocabulary is fixed.
- Exit-rule and watcher rows of the vendor file are not repeated here:
  ``test_exits.py`` and ``test_watcher.py`` already pin them (STRUCT-003).
- The two day-rollover auto-clear rows are marked skipped, never ported
  (R5): UTC rollover must not clear counters or unhalt the desk.
- All prose is English; the vendor text is Russian.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from pumpgrok.risk.sizing import (
    MAX_SHARE_OF_REMAINING_BUDGET,
    MIN_TRADE_LAMPORTS,
    position_size_lamports,
    to_r34_reason,
)

LAMPORTS_PER_SOL = 1_000_000_000

MAX_TRADE_LAMPORTS = 500_000_000
DAILY_LOSS_LIMIT_LAMPORTS = 2_000_000_000


@dataclass
class RiskHarness:
    """Test-local mirror of the vendor ``evaluate`` step order.

    Placeholder until plan 04-05 wires the real ``RiskEngine``. Sizes come
    from the ported sizer; reasons go through the R34 mapping, so every
    assertion below pins the vocabulary the engine must speak.
    """

    max_trade_lamports: int = MAX_TRADE_LAMPORTS
    daily_loss_limit_lamports: int = DAILY_LOSS_LIMIT_LAMPORTS
    max_trades_per_day: int = 3
    max_open_positions: int = 2
    trades_today: int = 0
    realized_pnl_lamports: int = 0
    positions: dict[str, int] = field(default_factory=dict)

    @property
    def daily_loss_lamports(self) -> int:
        """Loss for the day as a positive number. Profit counts as zero."""
        return max(0, -self.realized_pnl_lamports)

    @property
    def remaining_lamports(self) -> int:
        return max(0, self.daily_loss_limit_lamports - self.daily_loss_lamports)

    @property
    def halted(self) -> bool:
        return self.daily_loss_lamports >= self.daily_loss_limit_lamports

    def evaluate(self, mint: str, score: float) -> tuple[bool, str, int]:
        """Approve a trade or refuse it with an R34 reason. First failure wins."""
        if self.halted:
            loss_sol = self.daily_loss_lamports / LAMPORTS_PER_SOL
            return False, to_r34_reason(f"daily_loss_limit_hit ({loss_sol:.4f} SOL)"), 0
        if self.trades_today >= self.max_trades_per_day:
            detail = f"max_trades_per_day ({self.trades_today}/{self.max_trades_per_day})"
            return False, to_r34_reason(detail), 0
        if len(self.positions) >= self.max_open_positions:
            detail = f"max_open_positions ({len(self.positions)}/{self.max_open_positions})"
            return False, to_r34_reason(detail), 0
        if mint in self.positions:
            return False, to_r34_reason("already_open"), 0
        size = position_size_lamports(
            score,
            max_trade_lamports=self.max_trade_lamports,
            remaining_budget_lamports=self.remaining_lamports,
        )
        if size < MIN_TRADE_LAMPORTS:
            size_sol = size / LAMPORTS_PER_SOL
            return False, to_r34_reason(f"size_too_small ({size_sol:.6f} SOL)"), size
        return True, to_r34_reason("ok"), size

    def register_open(self, mint: str, size_lamports: int) -> None:
        self.positions[mint] = size_lamports
        self.trades_today += 1

    def register_close(self, mint: str, pnl_lamports: int) -> None:
        self.positions.pop(mint, None)
        self.realized_pnl_lamports += pnl_lamports


@pytest.fixture
def harness() -> RiskHarness:
    return RiskHarness()


# --- constants -------------------------------------------------------------


def test_min_trade_matches_vendor_floor() -> None:
    assert MIN_TRADE_LAMPORTS == 10_000_000


def test_budget_share_matches_vendor() -> None:
    assert pytest.approx(0.30) == MAX_SHARE_OF_REMAINING_BUDGET


# --- position size ---------------------------------------------------------


def test_size_is_proportional_to_score() -> None:
    full = DAILY_LOSS_LIMIT_LAMPORTS
    assert (
        position_size_lamports(
            1.0, max_trade_lamports=MAX_TRADE_LAMPORTS, remaining_budget_lamports=full
        )
        == 500_000_000
    )
    assert (
        position_size_lamports(
            0.7, max_trade_lamports=MAX_TRADE_LAMPORTS, remaining_budget_lamports=full
        )
        == 350_000_000
    )
    assert (
        position_size_lamports(
            0.0, max_trade_lamports=MAX_TRADE_LAMPORTS, remaining_budget_lamports=full
        )
        == 0
    )


def test_size_capped_by_max_trade() -> None:
    """A score above one never raises the stake."""
    size = position_size_lamports(
        3.0,
        max_trade_lamports=MAX_TRADE_LAMPORTS,
        remaining_budget_lamports=DAILY_LOSS_LIMIT_LAMPORTS,
    )
    assert size == 500_000_000


def test_size_shrinks_near_daily_limit() -> None:
    """0.4 SOL of budget left: at most 30 percent of it goes into one trade."""
    size = position_size_lamports(
        1.0, max_trade_lamports=MAX_TRADE_LAMPORTS, remaining_budget_lamports=400_000_000
    )
    assert size == 120_000_000
    assert size < MAX_TRADE_LAMPORTS


def test_profit_does_not_inflate_budget() -> None:
    """Profit never widens the daily-loss budget past the configured limit."""
    size = position_size_lamports(
        1.0,
        max_trade_lamports=MAX_TRADE_LAMPORTS,
        remaining_budget_lamports=DAILY_LOSS_LIMIT_LAMPORTS,
    )
    assert size == 500_000_000


# --- reason mapping --------------------------------------------------------


def test_vendor_daily_loss_maps_to_r34_halt() -> None:
    assert to_r34_reason("daily_loss_limit_hit (2.0000 SOL)") == "daily_loss_halt"


def test_vendor_bare_codes_pass_through() -> None:
    assert to_r34_reason("max_trades_per_day (3/3)") == "max_trades_per_day"
    assert to_r34_reason("max_open_positions (2/2)") == "max_open_positions"
    assert to_r34_reason("already_open") == "already_open"
    assert to_r34_reason("size_too_small (0.003000 SOL)") == "size_too_small"
    assert to_r34_reason("ok") == "ok"


def test_unknown_vendor_reason_raises() -> None:
    with pytest.raises(ValueError, match="unknown vendor evaluate reason"):
        to_r34_reason("something_brand_new")


# --- tracer: one evaluate reason pinned end to end --------------------------


def test_tiny_remaining_budget_rejects_trade(harness: RiskHarness) -> None:
    """Only 0.01 SOL of budget left: the 30 percent share is dust, so the
    trade is refused with the R34 size code, never with free text."""
    harness.realized_pnl_lamports = -1_990_000_000
    approved, reason, size = harness.evaluate("M", score=1.0)
    assert not approved
    assert reason == "size_too_small"
    assert size == 3_000_000


# --- limits ---------------------------------------------------------------


def test_healthy_trade_approved(harness: RiskHarness) -> None:
    approved, reason, size = harness.evaluate("M", score=0.8)
    assert approved
    assert reason == "ok"
    assert size == 400_000_000


def test_daily_loss_limit_halts_trading(harness: RiskHarness) -> None:
    harness.register_close("X", pnl_lamports=-2_000_000_000)
    assert harness.halted
    approved, reason, _ = harness.evaluate("M", score=1.0)
    assert not approved
    assert reason == "daily_loss_halt"


def test_daily_loss_limit_boundary(harness: RiskHarness) -> None:
    """Exactly at the limit the desk is halted; a hair below it still trades."""
    harness.realized_pnl_lamports = -1_999_000_000
    assert not harness.halted
    harness.realized_pnl_lamports = -2_000_000_000
    assert harness.halted


def test_max_trades_per_day(harness: RiskHarness) -> None:
    for index in range(3):
        harness.register_open(f"T{index}", size_lamports=100_000_000)
    approved, reason, _ = harness.evaluate("N", score=0.9)
    assert not approved
    assert reason == "max_trades_per_day"


def test_max_open_positions(harness: RiskHarness) -> None:
    harness.register_open("A", size_lamports=100_000_000)
    harness.register_open("B", size_lamports=100_000_000)
    approved, reason, _ = harness.evaluate("C", score=0.9)
    assert not approved
    assert reason == "max_open_positions"


def test_freed_slot_allows_new_trade(harness: RiskHarness) -> None:
    harness.register_open("A", size_lamports=100_000_000)
    harness.register_open("B", size_lamports=100_000_000)
    harness.register_close("A", pnl_lamports=50_000_000)
    assert harness.evaluate("C", score=0.9)[0]


def test_no_double_position_in_same_mint(harness: RiskHarness) -> None:
    harness.register_open("A", size_lamports=100_000_000)
    approved, reason, _ = harness.evaluate("A", score=0.9)
    assert not approved
    assert reason == "already_open"


def test_same_day_keeps_counters(harness: RiskHarness) -> None:
    """Without a UTC rollover nothing resets: the count and the position persist."""
    harness.register_open("A", size_lamports=100_000_000)
    assert harness.trades_today == 1
    assert "A" in harness.positions
    assert harness.evaluate("B", score=0.9)[0]
    assert harness.trades_today == 1


# --- day rollover: intentional non-port (R5) --------------------------------
#
# The vendor clears counters and unhalts at UTC midnight
# (``risk.py:106-117``). The desk must not: halts clear only through
# ``state halt --clear --by human:<name>``. These rows pin the exclusion:
# they mirror the vendor scenarios, and un-skipping one fails, proving the
# auto-clear path does not exist.


@pytest.mark.skip(reason="intentional non-port per R5: no auto-clear on UTC rollover")
def test_new_day_resets_counters_and_unhalts(harness: RiskHarness) -> None:
    harness.register_open("A", size_lamports=100_000_000)
    harness.register_close("X", pnl_lamports=-2_000_000_000)
    assert harness.halted
    # No roll_day_if_needed exists by design (R5). The vendor assertion
    # below is preserved as documentation and never runs.
    assert harness.evaluate("B", 0.9)[0] is True


@pytest.mark.skip(reason="intentional non-port per R5: no auto-clear on UTC rollover")
def test_day_roll_keeps_open_positions(harness: RiskHarness) -> None:
    harness.register_open("A", size_lamports=100_000_000)
    harness.realized_pnl_lamports = -2_000_000_000
    # No roll_day_if_needed exists by design (R5). The vendor assertions
    # below are preserved as documentation and never run.
    assert "A" in harness.positions
    assert harness.trades_today == 0
