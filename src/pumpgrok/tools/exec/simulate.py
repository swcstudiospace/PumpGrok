"""exec.simulate: dry-run a fill against observed liquidity (TOOL-004).

Pure-math preview through the bound ExecutionAdapter: no risk check, no
latency, no ledger writes on any path. Sells carry ``token_units`` (EXIT
rule engine) or ``size_lamports`` (SOL notional, derived at the curve).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from pumpgrok.core.adapter import ExecutionAdapter, Side
from pumpgrok.core.ids import Clock, ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import MintStr, meta_now

__all__ = [
    "SIMULATE_SPEC",
    "SimulateIn",
    "SimulateOut",
    "build_simulate_tool",
    "run_simulate",
]


class SimulateIn(ToolInput):
    """Simulate a fill for ``ticket_id`` without placing anything."""

    ticket_id: str = Field(pattern=r"^SOL-\d{8}-\d{3}$")
    mint: MintStr
    side: Literal["buy", "sell"]
    size_lamports: int | None = Field(default=None, gt=0)
    token_units: int | None = Field(default=None, gt=0)
    slippage_bps: int = Field(default=100, ge=0, le=10_000)
    quote_id: str | None = None

    @model_validator(mode="after")
    def _size_matches_side(self) -> Self:
        if self.side == "buy" and self.size_lamports is None:
            raise ValueError("buy requires size_lamports")
        if self.side == "sell" and self.token_units is None and self.size_lamports is None:
            raise ValueError("sell requires token_units or size_lamports")
        return self


class SimulateOut(ToolOutput):
    """Adapter preview mapped to the catalog shape (never a ledger row)."""

    would_fill: bool
    fill_kind: Literal["full", "partial", "rejected"]
    price_expected: Decimal
    expected_out: int = Field(ge=0)
    executed_size: int = Field(ge=0)
    price_impact: Decimal
    fee_lamports: int = Field(ge=0)
    priority_fee_lamports: int = Field(ge=0)
    liquidity_ratio: Decimal
    rejection_reason: (
        Literal[
            "below_liquidity_floor",
            "size_too_small",
            "post_graduation_no_reserves",
            "data_stale",
            "no_reserves",
        ]
        | None
    ) = None
    latency_ms_estimate: int = Field(ge=0)


SIMULATE_SPEC = ToolSpec(
    name="exec.simulate",
    description=(
        "Simulate a fill against observed liquidity without placing it. "
        "Pure curve math; never touches the ledger."
    ),
    input_model=SimulateIn,
    output_model=SimulateOut,
    side_effect=SideEffect.READ,
    timeout_s=10.0,
    rate_limit_key="solana_rpc",
    backend="pumpgrok.execution.paper_adapter.PaperAdapter.simulate",
)


async def run_simulate(inp: SimulateIn, adapter: ExecutionAdapter, clock: Clock) -> dict[str, Any]:
    """Preview the fill through the adapter; append nothing on any path."""
    result = await adapter.simulate(
        mint=inp.mint,
        side=Side(inp.side),
        size_lamports=inp.size_lamports,
        token_units=inp.token_units,
    )
    if inp.side == "buy":
        executed_size = int(inp.size_lamports or 0)
    elif inp.token_units is not None:
        executed_size = int(inp.token_units)
    else:
        executed_size = int(inp.size_lamports or 0)
    ambient = ambient_correlation()
    return SimulateOut.model_validate(
        {
            "would_fill": result.would_fill,
            "fill_kind": result.fill_kind,
            "price_expected": result.price_expected,
            "expected_out": result.expected_out,
            "executed_size": executed_size,
            "price_impact": result.price_impact_pct,
            "fee_lamports": result.venue_fee_lamports,
            "priority_fee_lamports": result.network_cost_lamports,
            "liquidity_ratio": result.liquidity_ratio,
            "rejection_reason": result.rejection_reason,
            "latency_ms_estimate": result.latency_ms_estimate,
            "meta": meta_now(
                "curve", inp.correlation_id or (str(ambient) if ambient else None), clock
            ),
        }
    ).model_dump()


def build_simulate_tool(adapter: ExecutionAdapter, clock: Clock) -> Tool:
    """Bind ``exec.simulate`` to one adapter and clock (no globals, no writes)."""

    @tool(SIMULATE_SPEC)
    async def _simulate(payload: SimulateIn) -> dict[str, Any]:
        return await run_simulate(payload, adapter, clock)

    return _simulate
