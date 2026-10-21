"""market.ohlcv: candles aggregated locally from the trade stream (TOOL-001).

The venue exposes no candle endpoint, so this tool fetches movements with
:func:`pumpgrok.tools.market.trades.fetch_trades` and buckets them into
``interval_s`` candles. The last bucket is always marked partial.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import J4, SOLANA_RPC_SOURCE, MintStr, meta_now
from pumpgrok.tools.market.trades import Trade, fetch_trades
from pumpgrok.tools.onchain.rpc import RpcClient, RpcError

_SIG_PAGE = 200


class Candle(BaseModel):
    """One bucket; prices are Decimal SOL per token."""

    model_config = ConfigDict(frozen=True)

    ts: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume_lamports: int = Field(ge=0)
    trades: int = Field(ge=0)


class OhlcvIn(ToolInput):
    """Candles for ``mint`` over ``interval_s``-second buckets."""

    mint: MintStr
    interval_s: Literal[15, 60, 300] = 60
    limit: int = Field(default=100, ge=1, le=500)


class OhlcvOut(ToolOutput):
    """Oldest-first candles; the trailing bucket is always partial."""

    candles: list[Candle]
    partial_last: bool


OHLCV_SPEC = ToolSpec(
    name="market.ohlcv",
    description=(
        "Candles for a mint aggregated locally from the RPC trade stream; "
        "the venue has no candle endpoint."
    ),
    input_model=OhlcvIn,
    output_model=OhlcvOut,
    side_effect=SideEffect.READ,
    timeout_s=10.0,
    retry=J4,
    rate_limit_key=SOLANA_RPC_SOURCE,
    backend="src/pumpgrok/tools/market/ohlcv.py via market.trades fetch",
)


def build_ohlcv(trades: list[Trade], interval_s: int, limit: int) -> list[Candle]:
    """Bucket trades oldest-first; pure function, no I/O (unit-pinned)."""
    buckets: dict[int, list[Trade]] = {}
    for trade in trades:
        if trade.token_units <= 0:
            continue
        bucket = trade.ts - (trade.ts % interval_s)
        buckets.setdefault(bucket, []).append(trade)
    candles: list[Candle] = []
    for bucket in sorted(buckets):
        bucket_trades = sorted(buckets[bucket], key=lambda t: t.ts)
        prices = [t.price_sol_per_token() for t in bucket_trades]
        candles.append(
            Candle(
                ts=bucket,
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume_lamports=sum(t.sol_lamports for t in bucket_trades),
                trades=len(bucket_trades),
            )
        )
    return candles[-limit:] if limit else []


async def run_ohlcv(inp: OhlcvIn, rpc: RpcClient) -> dict[str, Any]:
    """Fetch the trade stream and return a validated ``OhlcvOut`` payload."""
    try:
        trades = await fetch_trades(mint=inp.mint, rpc=rpc, limit=min(inp.limit, _SIG_PAGE))
    except RpcError as exc:
        raise DataStale(f"market.ohlcv upstream failed mint={inp.mint}") from exc
    candles = build_ohlcv(sorted(trades, key=lambda t: t.ts), inp.interval_s, inp.limit)
    out = {
        "candles": [c.model_dump() for c in candles],
        "partial_last": bool(candles),
        "meta": meta_now(
            SOLANA_RPC_SOURCE,
            inp.correlation_id or (str(a) if (a := ambient_correlation()) else None),
        ),
    }
    return OhlcvOut.model_validate(out).model_dump()


def build_ohlcv_tool(rpc: RpcClient) -> Tool:
    """Bind ``market.ohlcv`` to one injected RPC client (no globals)."""

    @tool(OHLCV_SPEC)
    async def _ohlcv(payload: OhlcvIn) -> dict[str, Any]:
        return await run_ohlcv(payload, rpc)

    return _ohlcv
