"""risk.check_limits: read-only view of the RiskEngine rule vocabulary (TOOL-005).

Reports every R34 rule in engine order with pass/fail/skip. Phase 3 has no
RiskEngine, so only structural checks evaluate (ledger consistency,
approval presence, size, seat budget); every engine rule reports ``skip``.
The enforcing run lives inside ``PaperAdapter.place`` in Phase 4 — this tool
authorises nothing.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore
from pumpgrok.tools._common import MintStr, meta_now

__all__ = [
    "CHECK_LIMITS_SPEC",
    "CheckLimitsIn",
    "CheckLimitsOut",
    "R34_RULE_IDS",
    "build_check_limits_tool",
    "run_check_limits",
]

R34_RULE_IDS: tuple[str, ...] = (
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


class CheckLimitsIn(ToolInput):
    """Prospective order to evaluate; ``bot`` echoes the seat under review."""

    ticket_id: str = Field(pattern=r"^SOL-\d{8}-\d{3}$")
    mint: MintStr
    side: Literal["buy", "sell"]
    size_lamports: int = Field(ge=0)
    decision_id: str | None = None
    approval_id: str | None = None
    bot: str | None = None


class CheckLimitsOut(ToolOutput):
    """One row per R34 rule in engine order; ``reason`` is the first fail."""

    approved: bool
    reason: str | None = None
    rules: list[dict] = Field(default_factory=list)
    limits: dict = Field(default_factory=dict)


CHECK_LIMITS_SPEC = ToolSpec(
    name="risk.check_limits",
    description=(
        "Evaluate a prospective order against the R20 budget vocabulary; "
        "structural checks only in Phase 3, engine rules skip."
    ),
    input_model=CheckLimitsIn,
    output_model=CheckLimitsOut,
    side_effect=SideEffect.READ,
    timeout_s=5.0,
    rate_limit_key="ledger",
    backend="pumpgrok.ledger.store.LedgerStore",
)


def _row(rule_id: str, status: str, value: object = None, limit: object = None) -> dict:
    return {"id": rule_id, "status": status, "value": value, "limit": limit}


async def run_check_limits(inp: CheckLimitsIn, store: LedgerStore, budget: RiskBudget) -> dict:
    """Evaluate structural checks; engine rules skip until Phase 4."""
    try:
        store.verify()
        ledger_status = "pass"
    except LedgerInconsistent:
        ledger_status = "fail"
    evaluations: dict[str, str] = dict.fromkeys(R34_RULE_IDS, "skip")
    evaluations["ledger_inconsistent"] = ledger_status
    evaluations["live_gate"] = "pass"
    evaluations["approval_missing"] = "fail" if inp.approval_id is None else "pass"
    evaluations["size_too_small"] = "fail" if inp.size_lamports == 0 else "pass"
    if inp.side == "buy" and not budget.may_open_exposure:
        evaluations["seat_may_trade"] = "fail"
    elif inp.side == "buy":
        evaluations["seat_may_trade"] = "pass"
    rules = [_row(rule_id, evaluations[rule_id]) for rule_id in R34_RULE_IDS]
    first_fail = next((r["id"] for r in rules if r["status"] == "fail"), None)
    ambient = ambient_correlation()
    limits = {
        "max_trade_fraction": str(budget.max_trade_fraction),
        "max_token_fraction": str(budget.max_token_fraction),
        "daily_loss_halt_fraction": str(budget.daily_loss_halt_fraction),
        "drawdown_halt_fraction": str(budget.drawdown_halt_fraction),
        "max_open_positions": budget.max_open_positions,
        "max_trades_per_day": budget.max_trades_per_day,
        "liquidity_floor_multiple": budget.liquidity_floor_multiple,
        "partial_fill_fraction": str(budget.partial_fill_fraction),
        "paper_equity_lamports": budget.paper_equity_lamports,
    }
    return CheckLimitsOut.model_validate(
        {
            "approved": first_fail is None,
            "reason": first_fail,
            "rules": rules,
            "limits": limits,
            "meta": meta_now("ledger", inp.correlation_id or (str(ambient) if ambient else None)),
        }
    ).model_dump()


def build_check_limits_tool(store: LedgerStore, budget: RiskBudget) -> Tool:
    """Bind ``risk.check_limits`` to one store and budget (no globals)."""

    @tool(CHECK_LIMITS_SPEC)
    async def _check_limits(payload: CheckLimitsIn) -> dict:
        return await run_check_limits(payload, store, budget)

    return _check_limits
