"""onchain.large_transfers: whale-sized movements from RPC (TOOL-002).

WHALE-only grant (R35); ``safety.score_report`` composes it in-process for
RUG. With no wallet list the tool resolves the top holders in-process and
uses them as the watch set. Each watched wallet contributes up to five
recent signatures; every fetched transaction is scanned for ``mint``
balance deltas at or above ``min_share`` of supply. ``kind`` is ``sell``
when the drained wallet also gained SOL, else ``transfer``; ``lp_remove``
is never emitted (no LP knowledge in Phase 3) and unresolvable
counterparties yield ``unknown``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import J5, SOLANA_RPC_SOURCE, MintStr, meta_now
from pumpgrok.tools.onchain.holders import holder_snapshot
from pumpgrok.tools.onchain.rpc import RpcClient, RpcError

_SIGS_PER_WALLET = 5


class Transfer(BaseModel):
    """One qualifying movement; money is int, share is 0..1 of supply."""

    model_config = ConfigDict(frozen=True)

    ts: int
    signature: str
    from_: str = Field(alias="from")
    to: str
    amount_units: int = Field(ge=0)
    share: Decimal = Field(ge=0, le=1)
    kind: Literal["sell", "transfer", "lp_remove", "unknown"]


class LargeTransfersIn(ToolInput):
    """Watch ``wallets`` (default: top holders) for ``mint`` movements."""

    mint: MintStr
    wallets: list[str] = Field(default_factory=list)
    min_share: Decimal = Field(default=Decimal("0.005"), ge=0)
    since_ts: int | None = None
    limit: int = Field(default=10, ge=1, le=20)


class LargeTransfersOut(ToolOutput):
    """Qualifying movements oldest-first."""

    transfers: list[Transfer]


LARGE_TRANSFERS_SPEC = ToolSpec(
    name="onchain.large_transfers",
    description=(
        "Whale-sized movements for a mint from parsed wallet "
        "transactions at or above a supply share threshold."
    ),
    input_model=LargeTransfersIn,
    output_model=LargeTransfersOut,
    side_effect=SideEffect.READ,
    timeout_s=20.0,
    retry=J5,
    rate_limit_key=SOLANA_RPC_SOURCE,
    backend="src/pumpgrok/tools/onchain/large_transfers.py via signatures+transactions",
)


async def _supply_units(mint: str, rpc: RpcClient) -> int:
    try:
        supply_res = await rpc.call("getTokenSupply", [mint])
        supply = int(supply_res["value"]["amount"])
    except (RpcError, KeyError, ValueError, TypeError) as exc:
        raise DataStale(f"onchain.large_transfers supply failed mint={mint}") from exc
    if supply <= 0:
        raise DataStale(f"onchain.large_transfers zero supply mint={mint}")
    return supply


def _account_keys(tx: dict[str, Any]) -> list[str]:
    """Account keys as plain strings; jsonParsed entries carry them under ``pubkey``."""
    message = tx.get("transaction", {}) if isinstance(tx.get("transaction"), dict) else {}
    raw_keys = message.get("message", {}).get("accountKeys", [])
    keys: list[str] = []
    for key in raw_keys if isinstance(raw_keys, list) else []:
        if isinstance(key, str):
            keys.append(key)
        elif isinstance(key, dict) and isinstance(key.get("pubkey"), str):
            keys.append(key["pubkey"])
    return keys


def _index_deltas(meta: dict[str, Any], mint: str) -> dict[int, int]:
    """Net ``mint`` units per token-account index across pre and post balances."""
    deltas: dict[int, int] = {}
    for side in ("preTokenBalances", "postTokenBalances"):
        balances = meta.get(side, [])
        if not isinstance(balances, list):
            continue
        for entry in balances:
            if not isinstance(entry, dict) or entry.get("mint") != mint:
                continue
            try:
                index = int(entry["accountIndex"])
                amount = int(entry.get("uiTokenAmount", {}).get("amount", "0"))
            except (KeyError, ValueError, TypeError, AttributeError):
                continue
            deltas[index] = deltas.get(index, 0) + (
                amount if side == "postTokenBalances" else -amount
            )
    return deltas


def _sol_delta_at(meta: dict[str, Any], index: int) -> int:
    """Lamport change of account ``index``; 0 when the balance arrays are unreadable."""
    pre_bal = meta.get("preBalances", [])
    post_bal = meta.get("postBalances", [])
    try:
        return int(post_bal[index]) - int(pre_bal[index])
    except (IndexError, ValueError, TypeError):
        return 0


def _transfer_kind(
    decrease_units: int, increase_units: int, from_sol_delta: int
) -> Literal["sell", "transfer", "unknown"]:
    """``sell`` when the drained wallet also gained SOL, else ``transfer``."""
    if decrease_units < 0:
        return "sell" if from_sol_delta > 0 else "transfer"
    if increase_units > 0 and decrease_units >= 0:
        return "transfer"
    return "unknown"


def parse_transfer_tx(
    mint: str,
    signature: str,
    wallet: str,
    tx: object,
    *,
    supply_units: int,
    min_share: Decimal,
) -> Transfer | None:
    """Extract the largest qualifying ``mint`` movement touching ``wallet``."""
    if not isinstance(tx, dict):
        return None
    meta = tx.get("meta")
    if not isinstance(meta, dict) or meta.get("err") is not None:
        return None
    keys = _account_keys(tx)
    deltas = _index_deltas(meta, mint)
    if not deltas:
        return None
    decrease_idx = min(deltas, key=lambda i: deltas[i])
    increase_idx = max(deltas, key=lambda i: deltas[i])
    amount = deltas[increase_idx]
    if amount <= 0 or Decimal(amount) < min_share * Decimal(supply_units):
        return None
    from_key = keys[decrease_idx] if 0 <= decrease_idx < len(keys) else ""
    to_key = keys[increase_idx] if 0 <= increase_idx < len(keys) else ""
    if not from_key or not to_key:
        return None
    kind = _transfer_kind(deltas[decrease_idx], amount, _sol_delta_at(meta, decrease_idx))
    ts = tx.get("blockTime")
    return Transfer.model_validate(
        {
            "ts": ts if isinstance(ts, int) else 0,
            "signature": signature,
            "from": from_key,
            "to": to_key,
            "amount_units": amount,
            "share": min(Decimal(1), Decimal(amount) / Decimal(supply_units)),
            "kind": kind,
        }
    )


async def run_large_transfers(inp: LargeTransfersIn, rpc: RpcClient) -> dict[str, Any]:
    """Scan watched wallets and return a validated typed payload."""
    supply = await _supply_units(inp.mint, rpc)
    if inp.wallets:
        wallets = list(inp.wallets)
    else:
        snap = await holder_snapshot(inp.mint, rpc, limit=10)
        if not snap.get("ok"):
            raise DataStale(f"onchain.large_transfers holders failed mint={inp.mint}")
        try:
            wallets = [str(e["address"]) for e in snap["holders"]]
        except (KeyError, TypeError) as exc:
            raise DataStale(f"onchain.large_transfers holders malformed mint={inp.mint}") from exc
    found: list[Transfer] = []
    for wallet in wallets[: inp.limit]:
        try:
            sigs = await rpc.call("getSignaturesForAddress", [wallet, {"limit": _SIGS_PER_WALLET}])
        except RpcError:
            continue
        if not isinstance(sigs, list):
            continue
        for entry in sigs:
            if not isinstance(entry, dict) or not isinstance(entry.get("signature"), str):
                continue
            block_time = entry.get("blockTime")
            ts = block_time if isinstance(block_time, int) else 0
            if inp.since_ts is not None and ts < inp.since_ts:
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
            transfer = parse_transfer_tx(
                inp.mint,
                entry["signature"],
                wallet,
                tx,
                supply_units=supply,
                min_share=inp.min_share,
            )
            if transfer is not None:
                found.append(transfer)
    found.sort(key=lambda t: t.ts)
    out = {
        "transfers": [t.model_dump(by_alias=True) for t in found],
        "meta": meta_now(
            SOLANA_RPC_SOURCE,
            inp.correlation_id or (str(a) if (a := ambient_correlation()) else None),
        ),
    }
    return LargeTransfersOut.model_validate(out).model_dump(by_alias=True)


def build_large_transfers_tool(rpc: RpcClient) -> Tool:
    """Bind ``onchain.large_transfers`` to one injected RPC client."""

    @tool(LARGE_TRANSFERS_SPEC)
    async def _large_transfers(payload: LargeTransfersIn) -> dict[str, Any]:
        return await run_large_transfers(payload, rpc)

    return _large_transfers
