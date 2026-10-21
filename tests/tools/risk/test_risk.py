"""RED: risk tools (check_limits/drawdown/kill_switch/halt_status) — TOOL-005.

- risk.kill_switch accepts only set|flatten_request (clear fails validation)
- risk.check_limits reports the R34 rule ids
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import pytest
from pydantic import ValidationError

from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.risk.check_limits import (
    CHECK_LIMITS_SPEC,
    R34_RULE_IDS,
    CheckLimitsIn,
    build_check_limits_tool,
)
from pumpgrok.tools.risk.drawdown import (
    DRAWDOWN_SPEC,
    DrawdownIn,
    build_drawdown_tool,
)
from pumpgrok.tools.risk.halt_status import (
    HALT_STATUS_SPEC,
    HaltStatusIn,
    build_halt_status_tool,
)
from pumpgrok.tools.risk.kill_switch import (
    KILL_SWITCH_SPEC,
    KillSwitchIn,
    build_kill_switch_tool,
    kill_switch_key,
)

START = 1469918176.385
TICKET = "SOL-20260201-001"
MINT = "So11111111111111111111111111111111111111112"


def _store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(str(tmp_path / "ledger.sqlite"))


def test_check_limits_reports_r34_rule_ids() -> None:
    assert CHECK_LIMITS_SPEC.side_effect is SideEffect.READ
    assert CHECK_LIMITS_SPEC.timeout_s == 5.0
    assert CHECK_LIMITS_SPEC.rate_limit_key == "ledger"
    assert list(R34_RULE_IDS) == [
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
    ]


async def test_check_limits_missing_approval_fails_closed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tool = build_check_limits_tool(store, RiskBudget())
    out = await tool(
        CheckLimitsIn(ticket_id=TICKET, mint=MINT, side="buy", size_lamports=100_000_000)
    )
    assert out.approved is False
    assert out.reason == "approval_missing"
    assert [r["id"] for r in out.rules] == list(R34_RULE_IDS)
    store.close()


async def test_drawdown_empty_ledger(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tool = build_drawdown_tool(store, RiskBudget())
    assert DRAWDOWN_SPEC.rate_limit_key == "ledger"
    out = await tool(DrawdownIn(window_hours=24))
    assert out.peak_equity_lamports == 0
    assert out.halted is False
    store.close()


def test_kill_switch_rejects_clear() -> None:
    assert KILL_SWITCH_SPEC.side_effect is SideEffect.PAPER_WRITE
    assert KILL_SWITCH_SPEC.rate_limit_key == "killswitch"
    with pytest.raises(ValidationError):
        KillSwitchIn(action="clear", reason="operator typo")


async def test_kill_switch_set_marks_active(tmp_path: Path) -> None:
    store = _store(tmp_path)
    clock = FixtureClock(start=START)
    tool = build_kill_switch_tool(store, clock)
    out = await tool(KillSwitchIn(action="set", reason="manual test"))
    assert out.active is True
    assert out.flatten_requested is False
    assert out.reason == "manual test"
    first_key = kill_switch_key("set", "manual test", clock)
    assert len(first_key) == 32
    store.close()


async def test_halt_status_combined_view(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tool = build_halt_status_tool(store, tmp_path / "KILLSWITCH", mode="paper")
    assert HALT_STATUS_SPEC.side_effect is SideEffect.READ
    out = await tool(HaltStatusIn())
    assert out.halted is False
    assert out.effective_mode == "paper"
    store.close()
