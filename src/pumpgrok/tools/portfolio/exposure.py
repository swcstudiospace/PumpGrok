"""portfolio.exposure: current exposure from ledger snapshots (TOOL-005).

Reads the latest snapshot for equity/cash and counts open positions from
``PositionOpened``/``PositionClosed`` events. Phase 3 has no mark engine, so
per-token exposure comes from open-position cost basis; curve marks land in
Phase 4. An empty ledger yields zeros, never an exception.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import Field

from pumpgrok.core.ids import Clock, ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.tools._common import MintStr, meta_now

__all__ = [
    "EXPOSURE_SPEC",
    "ExposureIn",
    "ExposureOut",
    "build_exposure_tool",
    "run_exposure",
]


class ExposureIn(ToolInput):
    """Filter to one mint; no mint returns every open position."""

    mint: MintStr | None = None


class ExposureOut(ToolOutput):
    """Equity, cash, gross exposure and per-token open exposure."""

    equity_lamports: int = Field(ge=0)
    cash_lamports: int = Field(ge=0)
    gross_exposure_lamports: int = Field(ge=0)
    gross_exposure_fraction: Decimal = Field(ge=0, le=1)
    open_positions: int = Field(ge=0)
    trades_today: int = Field(ge=0)
    per_token: list[dict] = Field(default_factory=list)


EXPOSURE_SPEC = ToolSpec(
    name="portfolio.exposure",
    description=(
        "Current exposure: equity, cash, gross fraction, open count and "
        "per-token cost basis from the ledger. Read only."
    ),
    input_model=ExposureIn,
    output_model=ExposureOut,
    side_effect=SideEffect.READ,
    timeout_s=5.0,
    rate_limit_key="ledger",
    backend="pumpgrok.ledger.store.LedgerStore",
)


def _today_utc(clock: Clock) -> str:
    return datetime.fromtimestamp(clock.now(), UTC).strftime("%Y-%m-%d")


async def run_exposure(inp: ExposureIn, store: LedgerStore, clock: Clock) -> dict:
    """Fold snapshots and position events into the exposure view."""
    snapshot = store.latest_snapshot()
    state = snapshot["state"] if snapshot else {}
    equity = int(state.get("equity_lamports", 0))
    cash = int(state.get("cash_lamports", 0))
    per_token: dict[str, int] = {}
    trades_today = 0
    today = _today_utc(clock)
    for event in store.read(limit=1000):
        payload = event["payload"]
        if event["type"] == "PositionOpened":
            mint = str(payload.get("mint", ""))
            per_token[mint] = per_token.get(mint, 0) + int(payload.get("cost_basis_lamports", 0))
        elif event["type"] == "PositionClosed":
            mint = str(payload.get("mint", ""))
            per_token.pop(mint, None)
        elif event["type"] == "FillRecorded" and str(event["ts_utc"]).startswith(today):
            trades_today += 1
    if inp.mint is not None:
        per_token = {m: v for m, v in per_token.items() if m == inp.mint}
    gross = sum(per_token.values())
    fraction = Decimal(gross) / Decimal(equity) if equity > 0 else Decimal("0")
    ambient = ambient_correlation()
    return ExposureOut.model_validate(
        {
            "equity_lamports": equity,
            "cash_lamports": cash,
            "gross_exposure_lamports": gross,
            "gross_exposure_fraction": min(fraction, Decimal("1")),
            "open_positions": len(per_token),
            "trades_today": trades_today,
            "per_token": [
                {"mint": mint, "exposure_lamports": lamports}
                for mint, lamports in sorted(per_token.items())
            ],
            "meta": meta_now("ledger", inp.correlation_id or (str(ambient) if ambient else None)),
        }
    ).model_dump()


def build_exposure_tool(store: LedgerStore, clock: Clock) -> Tool:
    """Bind ``portfolio.exposure`` to one store and clock (no globals)."""

    @tool(EXPOSURE_SPEC)
    async def _exposure(payload: ExposureIn) -> dict:
        return await run_exposure(payload, store, clock)

    return _exposure
