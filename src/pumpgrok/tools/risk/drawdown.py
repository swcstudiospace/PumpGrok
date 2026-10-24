"""risk.drawdown: drawdown from peak equity and loss velocity (TOOL-005).

Folds the current ledger state (every event, not a stale snapshot) and reads
equity and drawdown through the shared ``ledger.views``. An empty ledger
yields zeros; ``halted`` compares the drawdown against the injected budget
fraction.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import Field

from pumpgrok.core.ids import Clock, ambient_correlation
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.views import drawdown_fraction, equity_lamports
from pumpgrok.tools._common import fold_current_state, meta_now

__all__ = [
    "DRAWDOWN_SPEC",
    "DrawdownIn",
    "DrawdownOut",
    "build_drawdown_tool",
    "run_drawdown",
]


class DrawdownIn(ToolInput):
    """Window for the peak scan, in hours."""

    window_hours: int = Field(default=24, ge=1, le=168)


class DrawdownOut(ToolOutput):
    """Peak/current equity, drawdown fraction and loss velocity."""

    peak_equity_lamports: int = Field(ge=0)
    current_equity_lamports: int = Field(ge=0)
    drawdown_fraction: Decimal = Field(ge=0, le=1)
    loss_velocity_lamports_per_h: int = 0
    halted: bool = False


DRAWDOWN_SPEC = ToolSpec(
    name="risk.drawdown",
    description=(
        "Drawdown from peak equity and loss per hour for the loss_velocity "
        "breaker. Read only; snapshots are the source."
    ),
    input_model=DrawdownIn,
    output_model=DrawdownOut,
    side_effect=SideEffect.READ,
    timeout_s=5.0,
    rate_limit_key="ledger",
    backend="pumpgrok.ledger.store.LedgerStore",
)


async def run_drawdown(
    inp: DrawdownIn, store: LedgerStore, budget: RiskBudget, clock: Clock
) -> dict[str, Any]:
    """Current equity against the folded peak; an empty ledger yields zeros."""
    state = fold_current_state(store, clock, budget)
    current = equity_lamports(state)
    peak = max(int(state.peak_equity_lamports), current)
    drawdown = max(drawdown_fraction(state), Decimal("0"))
    loss_velocity = max(peak - current, 0) // inp.window_hours
    ambient = ambient_correlation()
    return DrawdownOut.model_validate(
        {
            "peak_equity_lamports": peak,
            "current_equity_lamports": current,
            "drawdown_fraction": drawdown,
            "loss_velocity_lamports_per_h": loss_velocity,
            "halted": drawdown >= budget.drawdown_halt_fraction,
            "meta": meta_now(
                "ledger", inp.correlation_id or (str(ambient) if ambient else None), clock
            ),
        }
    ).model_dump()


def build_drawdown_tool(store: LedgerStore, budget: RiskBudget, clock: Clock) -> Tool:
    """Bind ``risk.drawdown`` to one store, budget and clock (no globals)."""

    @tool(DRAWDOWN_SPEC)
    async def _drawdown(payload: DrawdownIn) -> dict[str, Any]:
        return await run_drawdown(payload, store, budget, clock)

    return _drawdown
