"""market.trades: recent token transfers from Solana RPC (TOOL-001, B9).

Reads ``getSignaturesForAddress`` on the mint, then ``getTransaction``
(jsonParsed) per signature, and classifies each qualifying movement as a
buy (tokens in, SOL out) or a sell (tokens out, SOL in). No REST fallback
and no websocket tail exist in this module (R44, R46, R47).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import J4, SOLANA_RPC_SOURCE, MintStr, meta_now
from pumpgrok.tools.onchain.rpc import RpcClient, RpcError

_TX_LIMIT_PER_MINT = 200


class Trade(BaseModel):
    """One classified movement; money is int, price is derived Decimal."""

    model_config = ConfigDict(frozen=True)

    ts: int
    side: Literal["buy", "sell"]
    wallet: str
    sol_lamports: int = Field(ge=0)
    token_units: int = Field(ge=0)
    signature: str | None = None

    def price_sol_per_token(self) -> Decimal:
        """SOL per token for this movement (wrapper-boundary Decimal math)."""
        if self.token_units <= 0:
            return Decimal(0)
        return (
            Decimal(self.sol_lamports)
            / Decimal(self.token_units)
            * Decimal(1_000_000)
            / Decimal(1_000_000_000)
        )


class TradesIn(ToolInput):
    """Recent trades for ``mint``; ``since_ts`` drops older entries."""

    mint: MintStr
    limit: int = Field(default=200, ge=1, le=200)
    since_ts: int | None = None


class TradesOut(ToolOutput):
    """Classified trades with the buy/sell count ratio."""

    trades: list[Trade]
    buy_sell_ratio: Decimal
    unique_wallets: int = Field(ge=0)


TRADES_SPEC = ToolSpec(
    name="market.trades",
    description=(
        "Recent trades for a mint from RPC signatures and parsed "
        "transactions, classified buy/sell by token and SOL flow."
    ),
    input_model=TradesIn,
    output_model=TradesOut,
    side_effect=SideEffect.READ,
    timeout_s=10.0,
    retry=J4,
    rate_limit_key=SOLANA_RPC_SOURCE,
    backend="src/pumpgrok/tools/market/trades.py via solana_rpc signatures",
)


def _pubkeys(message: object) -> list[str]:
    keys = message.get("accountKeys", []) if isinstance(message, dict) else []
    out: list[str] = []
    for key in keys:
        if isinstance(key, str):
            out.append(key)
        elif isinstance(key, dict) and isinstance(key.get("pubkey"), str):
            out.append(key["pubkey"])
    return out


def parse_trade_tx(mint: str, signature: str, fallback_ts: int, tx: object) -> Trade | None:
    """Classify one parsed transaction; ``None`` when it is not a trade."""
    if not isinstance(tx, dict):
        return None
    meta = tx.get("meta")
    if not isinstance(meta, dict) or meta.get("err") is not None:
        return None
    message = (
        tx.get("transaction", {}).get("message", {})
        if isinstance(tx.get("transaction"), dict)
        else {}
    )
    keys = _pubkeys(message)
    if not keys:
        return None
    pre_bal = meta.get("preBalances", [])
    post_bal = meta.get("postBalances", [])
    if not isinstance(pre_bal, list) or not isinstance(post_bal, list):
        return None
    try:
        sol_delta = int(post_bal[0]) - int(pre_bal[0])
    except (IndexError, ValueError, TypeError):
        return None
    token_net = 0
    for side in ("preTokenBalances", "postTokenBalances"):
        balances = meta.get(side, [])
        if not isinstance(balances, list):
            continue
        for entry in balances:
            if not isinstance(entry, dict) or entry.get("mint") != mint:
                continue
            try:
                amount = int(entry.get("uiTokenAmount", {}).get("amount", "0"))
            except (ValueError, TypeError, AttributeError):
                continue
            token_net += amount if side == "postTokenBalances" else -amount
    if token_net > 0 and sol_delta < 0:
        side: Literal["buy", "sell"] = "buy"
    elif token_net < 0 and sol_delta > 0:
        side = "sell"
    else:
        return None
    ts = tx.get("blockTime")
    return Trade(
        ts=ts if isinstance(ts, int) else fallback_ts,
        side=side,
        wallet=keys[0],
        sol_lamports=abs(sol_delta),
        token_units=abs(token_net),
        signature=signature,
    )


async def fetch_trades(
    mint: str, rpc: RpcClient, *, limit: int = 200, since_ts: int | None = None
) -> list[Trade]:
    """Fetch and classify up to ``limit`` movements for ``mint`` (RPC only)."""
    try:
        sigs = await rpc.call(
            "getSignaturesForAddress", [mint, {"limit": min(limit, _TX_LIMIT_PER_MINT)}]
        )
    except RpcError as exc:
        raise DataStale(f"market.trades signatures failed mint={mint}") from exc
    if not isinstance(sigs, list):
        raise DataStale(f"market.trades signatures malformed mint={mint}")
    trades: list[Trade] = []
    for entry in sigs[:limit]:
        if not isinstance(entry, dict) or not isinstance(entry.get("signature"), str):
            continue
        block_time = entry.get("blockTime")
        ts = block_time if isinstance(block_time, int) else 0
        if since_ts is not None and ts < since_ts:
            continue
        try:
            tx = await rpc.call(
                "getTransaction",
                [
                    entry["signature"],
                    {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
                ],
            )
        except RpcError:
            continue
        trade = parse_trade_tx(mint, entry["signature"], ts, tx)
        if trade is not None:
            trades.append(trade)
    return trades


async def run_trades(inp: TradesIn, rpc: RpcClient) -> dict:
    """Return a validated ``TradesOut`` payload for ``inp``."""
    trades = await fetch_trades(mint=inp.mint, rpc=rpc, limit=inp.limit, since_ts=inp.since_ts)
    buys = sum(1 for t in trades if t.side == "buy")
    sells = sum(1 for t in trades if t.side == "sell")
    ratio = Decimal(buys) / Decimal(sells) if sells else Decimal(buys)
    out = {
        "trades": [t.model_dump() for t in trades],
        "buy_sell_ratio": ratio,
        "unique_wallets": len({t.wallet for t in trades}),
        "meta": meta_now(
            SOLANA_RPC_SOURCE,
            inp.correlation_id or (str(a) if (a := ambient_correlation()) else None),
        ),
    }
    return TradesOut.model_validate(out).model_dump()


def build_trades_tool(rpc: RpcClient) -> Tool:
    """Bind ``market.trades`` to one injected RPC client (no globals)."""

    @tool(TRADES_SPEC)
    async def _trades(payload: TradesIn) -> dict:
        return await run_trades(payload, rpc)

    return _trades
