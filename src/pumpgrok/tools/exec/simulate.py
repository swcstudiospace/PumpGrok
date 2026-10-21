"""exec.simulate: dry-run a fill against observed liquidity (TOOL-004).

Phase 3 scope: input validation only. The PaperAdapter simulation (fill
model, liquidity floor, slippage recompute) is Phase 4 work, so a valid shape
raises ``not_yet_implemented``. This tool never touches the ledger on any
path: it takes no store and appends nothing.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, model_validator

from pumpgrok.core.errors import NotYetImplemented
from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import MintStr

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
        if self.side == "sell" and self.token_units is None:
            raise ValueError("sell requires token_units")
        return self


class SimulateOut(ToolOutput):
    """Simulation result; unreachable in Phase 3 (kept for Phase 4)."""

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
            "below_liquidity_floor", "size_too_small", "post_graduation_no_reserves", "data_stale"
        ]
        | None
    ) = None
    latency_ms_estimate: int = Field(ge=0)


SIMULATE_SPEC = ToolSpec(
    name="exec.simulate",
    description=(
        "Simulate a fill against observed liquidity without placing it. "
        "Phase 3 validates the input only; the fill model is Phase 4 work."
    ),
    input_model=SimulateIn,
    output_model=SimulateOut,
    side_effect=SideEffect.READ,
    timeout_s=10.0,
    rate_limit_key="solana_rpc",
    backend="phase-4-paper-adapter-simulate",
)


async def run_simulate(inp: SimulateIn) -> dict:
    """Validate the input, then refuse: the fill model is Phase 4 work.

    Takes no store and appends nothing, so zero ledger events on every path.
    """
    ambient = ambient_correlation()
    raise NotYetImplemented(
        "exec.simulate needs the Phase 4 PaperAdapter fill model",
        tool="exec.simulate",
        ticket_id=inp.ticket_id,
        correlation_id=inp.correlation_id or (str(ambient) if ambient else "none"),
    )


def build_simulate_tool() -> Tool:
    """Bind ``exec.simulate`` (no backend in Phase 3, no globals)."""

    @tool(SIMULATE_SPEC)
    async def _simulate(payload: SimulateIn) -> dict:
        return await run_simulate(payload)

    return _simulate
