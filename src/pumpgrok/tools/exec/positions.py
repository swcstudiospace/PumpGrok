"""exec.positions: open paper positions with mark-to-market (TOOL-004).

Read-only view over the ExecutionAdapter: positions from the adapter plus
ledger-fold equity and cash. Never appends.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from pumpgrok.core.adapter import ExecutionAdapter
from pumpgrok.core.ids import Clock, ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import MintStr, meta_now

__all__ = [
    "POSITIONS_SPEC",
    "PositionsIn",
    "PositionsOut",
    "build_positions_tool",
    "run_positions",
]


class PositionsIn(ToolInput):
    """Filter open positions; no filter returns every open position."""

    mint: MintStr | None = None
    include_closed_since_ts: int | None = Field(default=None, ge=0)


class PositionsOut(ToolOutput):
    """Open positions with ledger-fold equity and cash."""

    positions: list[dict[str, str | int | bool]] = Field(default_factory=list)
    equity_lamports: int = Field(default=0, ge=0)
    cash_lamports: int = Field(default=0, ge=0)


POSITIONS_SPEC = ToolSpec(
    name="exec.positions",
    description=(
        "Open paper positions with mark-to-market from the latest curve price, "
        "plus ledger-fold equity and cash."
    ),
    input_model=PositionsIn,
    output_model=PositionsOut,
    side_effect=SideEffect.READ,
    timeout_s=10.0,
    rate_limit_key="ledger",
    backend="pumpgrok.execution.paper_adapter.PaperAdapter.positions",
)


async def run_positions(
    inp: PositionsIn, adapter: ExecutionAdapter, clock: Clock
) -> dict[str, Any]:
    """Open positions plus ledger-fold equity and cash (all integer lamports)."""
    positions = await adapter.positions(inp.mint)
    ambient = ambient_correlation()
    rows = [
        {
            "ticket_id": position.ticket_id,
            "mint": position.mint,
            "mtm_frozen": position.mtm_frozen,
            "unrealised_pnl_lamports": position.unrealised_pnl_lamports,
        }
        for position in positions
    ]
    return PositionsOut.model_validate(
        {
            "positions": rows,
            "equity_lamports": adapter.equity_lamports(),
            "cash_lamports": adapter.cash_lamports(),
            "meta": meta_now(
                "ledger", inp.correlation_id or (str(ambient) if ambient else None), clock
            ),
        }
    ).model_dump()


def build_positions_tool(adapter: ExecutionAdapter, clock: Clock) -> Tool:
    """Bind ``exec.positions`` to one adapter and clock (no globals)."""

    @tool(POSITIONS_SPEC)
    async def _positions(payload: PositionsIn) -> dict[str, Any]:
        return await run_positions(payload, adapter, clock)

    return _positions
