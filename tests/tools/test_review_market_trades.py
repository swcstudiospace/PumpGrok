"""Regression: ordinary swaps must classify as trades (review finding 21).

A swap moves tokens from the pool's token account to the buyer's account. The
mint's per-account changes therefore net to zero across all accounts; only the
trader's own change (by owner, or by the SOL-matching side) classifies it.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

from pumpgrok.core.errors import DataStale
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.market.trades import fetch_trades, parse_trade_tx
from pumpgrok.tools.onchain.rpc import RpcClient

MINT = "M" * 44
TRADER = "T" * 44
POOL = "P" * 44
OTHER = "O" * 44


def _balance(index: int, amount: int, owner: str | None) -> dict:
    entry: dict = {"accountIndex": index, "mint": MINT, "uiTokenAmount": {"amount": str(amount)}}
    if owner is not None:
        entry["owner"] = owner
    return entry


def _tx(
    *,
    sol_pre: int,
    sol_post: int,
    pre_tokens: list[dict],
    post_tokens: list[dict],
    keys: list[str],
) -> dict:
    return {
        "blockTime": 1_000,
        "meta": {
            "err": None,
            "preBalances": [sol_pre, 0, 0],
            "postBalances": [sol_post, 0, 0],
            "preTokenBalances": pre_tokens,
            "postTokenBalances": post_tokens,
        },
        "transaction": {"message": {"accountKeys": [{"pubkey": k} for k in keys]}},
    }


def test_buy_with_owner_data_is_classified() -> None:
    # Trader pays SOL and its token account gains 1_000_000; the pool's account loses it.
    tx = _tx(
        sol_pre=100,
        sol_post=90,
        pre_tokens=[_balance(1, 0, TRADER), _balance(2, 9_000_000, POOL)],
        post_tokens=[_balance(1, 1_000_000, TRADER), _balance(2, 8_000_000, POOL)],
        keys=[TRADER, POOL, OTHER],
    )
    trade = parse_trade_tx(MINT, "sig-buy", 0, tx)
    assert trade is not None
    assert trade.side == "buy"
    assert trade.wallet == TRADER
    assert trade.token_units == 1_000_000
    assert trade.sol_lamports == 10


def test_sell_with_owner_data_is_classified() -> None:
    # Trader receives SOL and its token account loses 500_000 to the pool.
    tx = _tx(
        sol_pre=90,
        sol_post=95,
        pre_tokens=[_balance(1, 500_000, TRADER), _balance(2, 1_000_000, POOL)],
        post_tokens=[_balance(1, 0, TRADER), _balance(2, 1_500_000, POOL)],
        keys=[TRADER, POOL],
    )
    trade = parse_trade_tx(MINT, "sig-sell", 0, tx)
    assert trade is not None
    assert trade.side == "sell"
    assert trade.token_units == 500_000
    assert trade.sol_lamports == 5


def test_buy_without_owner_data_is_classified() -> None:
    # No owner field: the trader is the side whose change matches the SOL direction.
    tx = _tx(
        sol_pre=100,
        sol_post=90,
        pre_tokens=[_balance(2, 9_000_000, None)],
        post_tokens=[_balance(1, 1_000_000, None), _balance(2, 8_000_000, None)],
        keys=[TRADER, POOL],
    )
    trade = parse_trade_tx(MINT, "sig-buy-noowner", 0, tx)
    assert trade is not None
    assert trade.side == "buy"
    assert trade.token_units == 1_000_000


def test_pool_only_movement_without_trader_is_not_a_trade() -> None:
    # Tokens move between two other accounts; the fee payer's token balance is unchanged.
    tx = _tx(
        sol_pre=100,
        sol_post=90,
        pre_tokens=[_balance(1, 0, TRADER), _balance(2, 9_000_000, POOL)],
        post_tokens=[_balance(1, 0, TRADER), _balance(2, 8_000_000, POOL)],
        keys=[TRADER, POOL],
    )
    assert parse_trade_tx(MINT, "sig-none", 0, tx) is None


START = 1469918176.385
RpcAnswer = Callable[[str, list[Any]], Awaitable[Any]]


class _RpcFailure(Exception):
    """Scripted RPC-level failure for one request."""


def _buy_tx(block_time: int | None) -> dict:
    tx = _tx(
        sol_pre=100,
        sol_post=90,
        pre_tokens=[_balance(1, 0, TRADER), _balance(2, 9_000_000, POOL)],
        post_tokens=[_balance(1, 1_000_000, TRADER), _balance(2, 8_000_000, POOL)],
        keys=[TRADER, POOL, OTHER],
    )
    if block_time is None:
        del tx["blockTime"]
    else:
        tx["blockTime"] = block_time
    return tx


def _answer(
    signatures: list[dict],
    transactions: dict[str, dict],
    failing: frozenset[str] = frozenset(),
) -> RpcAnswer:
    async def answer(method: str, params: list[Any]) -> Any:
        if method == "getSignaturesForAddress":
            return signatures
        if params[0] in failing:
            raise _RpcFailure
        return transactions.get(params[0])

    return answer


def _rpc(answer: RpcAnswer) -> RpcClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        try:
            result = await answer(body["method"], body["params"])
        except _RpcFailure:
            error = {"code": -32005, "message": "unavailable"}
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": body.get("id"), "error": error}
            )
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body.get("id"), "result": result})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return RpcClient(
        ["https://a.invalid", "https://b.invalid"],
        client,
        FixtureClock(start=START),
        rng=random.Random(5),
    )


async def test_failed_transaction_fetch_raises_instead_of_dropping_the_trade() -> None:
    signatures = [{"signature": "s1", "blockTime": 1000}, {"signature": "s2", "blockTime": 1060}]
    rpc = _rpc(_answer(signatures, {"s1": _buy_tx(1000)}, failing=frozenset({"s2"})))
    with pytest.raises(DataStale):
        await fetch_trades(MINT, rpc)


async def test_movement_without_block_time_is_not_placed_at_epoch() -> None:
    signatures = [{"signature": "s1", "blockTime": 1000}, {"signature": "s2"}]
    rpc = _rpc(_answer(signatures, {"s1": _buy_tx(1000), "s2": _buy_tx(None)}))
    trades = await fetch_trades(MINT, rpc)
    assert [t.signature for t in trades] == ["s1"]


async def test_transaction_fetches_overlap_within_the_tool_timeout() -> None:
    signatures = [{"signature": f"s{i}", "blockTime": 1000 + i} for i in range(8)]
    in_flight = 0
    peak = 0
    overlapped = asyncio.Event()

    async def answer(method: str, params: list[Any]) -> Any:
        nonlocal in_flight, peak
        if method == "getSignaturesForAddress":
            return signatures
        in_flight += 1
        peak = max(peak, in_flight)
        if in_flight >= 4:
            overlapped.set()
        await overlapped.wait()
        in_flight -= 1
        return _buy_tx(1000)

    trades = await asyncio.wait_for(fetch_trades(MINT, _rpc(answer)), timeout=5)
    assert len(trades) == 8
    assert peak >= 4
