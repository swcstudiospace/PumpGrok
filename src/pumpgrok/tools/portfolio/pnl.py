"""portfolio.pnl: realised and unrealised PnL for a window (TOOL-005).

Folds ``FillRecorded`` fees and ``PositionClosed`` realised PnL from the
ledger. Marks (unrealised, drawdown) need the Phase 4 mark engine, so they
are zero until snapshots carry them; day-start and peak equity come from the
latest snapshot when present. An empty ledger yields zeros, never an
exception.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field

from pumpgrok.core.ids import Clock, ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.tools._common import meta_now

__all__ = [
    "PNL_SPEC",
    "PnlIn",
    "PnlOut",
    "build_pnl_tool",
    "run_pnl",
]


class PnlIn(ToolInput):
    """Window for the PnL fold; ``as_of`` pins the window end (UTC)."""

    window: Literal["day", "week", "all"] = "day"
    as_of: datetime | None = None


class PnlOut(ToolOutput):
    """Realised/fees folded from events; unrealised zero until Phase 4 marks."""

    realised_lamports: int
    unrealised_lamports: int = 0
    fees_lamports: int = Field(ge=0)
    daily_loss_fraction: Decimal = Field(ge=0)
    day_start_equity_lamports: int = Field(ge=0)
    peak_equity_lamports: int = Field(ge=0)
    drawdown_fraction: Decimal = Field(ge=0, le=1)
    trades: int = Field(ge=0)
    closed_trades: int = Field(ge=0)
    win_rate: Decimal | None = None
    profit_factor: Decimal | None = None


PNL_SPEC = ToolSpec(
    name="portfolio.pnl",
    description=(
        "Realised and unrealised PnL for a window with daily-loss fraction "
        "and drawdown. Read only; marks are Phase 4."
    ),
    input_model=PnlIn,
    output_model=PnlOut,
    side_effect=SideEffect.READ,
    timeout_s=5.0,
    rate_limit_key="ledger",
    backend="pumpgrok.ledger.store.LedgerStore",
)


async def run_pnl(inp: PnlIn, store: LedgerStore, clock: Clock) -> dict[str, Any]:
    """Fold fills and closes into the window summary."""
    as_of = inp.as_of or datetime.fromtimestamp(clock.now(), UTC)
    realised = 0
    fees = 0
    trades = 0
    closed = 0
    wins = 0
    gross_profit = 0
    gross_loss = 0
    for event in store.read(limit=1000):
        payload = event["payload"]
        if event["type"] == "FillRecorded":
            trades += 1
            fees += int(payload.get("venue_fee_lamports", 0))
            fees += int(payload.get("network_cost_lamports", 0))
        elif event["type"] == "PositionClosed":
            closed += 1
            pnl = int(payload.get("realized_pnl_lamports", 0))
            realised += pnl
            if pnl > 0:
                wins += 1
                gross_profit += pnl
            elif pnl < 0:
                gross_loss += -pnl
    snapshot = store.latest_snapshot()
    state = snapshot["state"] if snapshot else {}
    day_start = int(state.get("day_start_equity_lamports", state.get("equity_lamports", 0)))
    peak = int(state.get("peak_equity_lamports", day_start))
    _ = as_of  # Window slicing over event days is Phase 4; the fold covers the ledger.
    ambient = ambient_correlation()
    return PnlOut.model_validate(
        {
            "realised_lamports": realised,
            "unrealised_lamports": 0,
            "fees_lamports": fees,
            "daily_loss_fraction": Decimal("0"),
            "day_start_equity_lamports": day_start,
            "peak_equity_lamports": peak,
            "drawdown_fraction": Decimal("0"),
            "trades": trades,
            "closed_trades": closed,
            "win_rate": (Decimal(wins) / Decimal(closed) if closed else None),
            "meta": meta_now(
                "ledger", inp.correlation_id or (str(ambient) if ambient else None), clock
            ),
        }
    ).model_dump()


def build_pnl_tool(store: LedgerStore, clock: Clock) -> Tool:
    """Bind ``portfolio.pnl`` to one store and clock (no globals)."""

    @tool(PNL_SPEC)
    async def _pnl(payload: PnlIn) -> dict[str, Any]:
        return await run_pnl(payload, store, clock)

    return _pnl
