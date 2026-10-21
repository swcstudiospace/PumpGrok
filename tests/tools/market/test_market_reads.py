"""Market READ tools over RPC fixtures (Phase 3 plan 03-02, task 2 RED).

Covers market.ohlcv, market.liquidity, market.trades and
market.holders_snapshot: every output carries meta.source and
meta.freshness_s, unknown input fields are rejected, and no test touches
live network (single MockTransport handler only).
"""

from __future__ import annotations

import base64
import json
import random
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import httpx

from pumpgrok.core.bot import BotManifest, ToolGrant
from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools import build_registry, register_read_tools
from pumpgrok.tools.market.holders_snapshot import HoldersSnapshotIn
from pumpgrok.tools.market.liquidity import LiquidityIn
from pumpgrok.tools.market.ohlcv import OhlcvIn, build_ohlcv
from pumpgrok.tools.market.trades import TradesIn
from pumpgrok.tools.onchain.curve_layout import CURVE_ACCOUNT_SIZE, encode_curve_fixture
from pumpgrok.tools.onchain.rpc import RpcClient

START = 1469918176.385
MINT = "So11111111111111111111111111111111111111112"
CURVE = "8" * 44
W1 = "1" * 44
W2 = "2" * 44

VSOL = 30_000_000_000
VTOK = 1_000_000_000_000_000
SUPPLY = 1_000_000_000_000_000


def _curve_b64() -> str:
    raw = encode_curve_fixture(
        virtual_sol_reserves_lamports=VSOL,
        virtual_token_reserves_units=VTOK,
        real_sol_reserves_lamports=VSOL,
        real_token_reserves_units=970_000_000_000_000,
        total_supply_units=SUPPLY,
        complete=False,
    )
    assert len(raw) == CURVE_ACCOUNT_SIZE
    return base64.b64encode(raw).decode("ascii")


def _tx(keys: list[str], pre_sol: list[int], post_sol: list[int], pre_tok: list[tuple[int, str]], post_tok: list[tuple[int, str]], ts: int) -> dict:
    def _bal(side: list[tuple[int, str]]) -> list[dict]:
        return [
            {"accountIndex": i, "mint": MINT, "uiTokenAmount": {"amount": a}}
            for i, a in side
        ]

    return {
        "blockTime": ts,
        "meta": {
            "err": None,
            "preBalances": pre_sol,
            "postBalances": post_sol,
            "preTokenBalances": _bal(pre_tok),
            "postTokenBalances": _bal(post_tok),
        },
        "transaction": {"message": {"accountKeys": [{"pubkey": k} for k in keys]}},
    }


_TX1 = _tx([W1, "C" * 44], [100, 0], [90, 0], [], [(1, "1000000")], 1000)
_TX2 = _tx([W2, "C" * 44], [90, 0], [95, 0], [(0, "500000")], [], 1060)

_HOLDERS = {
    "value": [
        {"address": "A" * 44, "uiAmount": 50.0, "decimals": 6},
        {"address": "B" * 44, "uiAmount": 30.0, "decimals": 6},
        {"address": "C" * 44, "uiAmount": 20.0, "decimals": 6},
    ]
}


def _rpc() -> RpcClient:
    curve = _curve_b64()

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        method, params = body["method"], body["params"]
        if method == "getSignaturesForAddress":
            result = [
                {"signature": "s1", "slot": 1, "blockTime": 1000},
                {"signature": "s2", "slot": 2, "blockTime": 1060},
            ]
        elif method == "getTransaction":
            result = _TX1 if params[0] == "s1" else _TX2
        elif method == "getTokenLargestAccounts":
            result = _HOLDERS
        elif method == "getAccountInfo":
            result = {
                "context": {"slot": 7},
                "value": {
                    "data": [curve, "base64"],
                    "executable": False,
                    "lamports": 1,
                    "owner": "o",
                    "rentEpoch": 1,
                },
            }
        else:
            raise AssertionError(f"unexpected method {method}")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    client = httpx.AsyncClient(transport=transport)
    return RpcClient(
        ["https://rpc.invalid"],
        client,
        FixtureClock(start=START),
        rng=random.Random(5),
    )


def _registry():
    reg, _ = build_registry(clock=FixtureClock(start=START), rng=random.Random(11))
    register_read_tools(reg, _rpc())
    return reg


def _bot() -> BotManifest:
    names = ["market.price", "market.ohlcv", "market.liquidity", "market.trades",
             "market.holders_snapshot"]
    return BotManifest(
        id="bot-01-scout",
        display="scout",
        channel="DM",
        purpose="test seat",
        inputs=[],
        outputs=[],
        skills=[],
        allowed_tools=[ToolGrant(name=n, side_effect=SideEffect.READ) for n in names],
        risk_budget={},
        forbidden=[],
        fail_safe="halt",
        schedule=[],
        escalation=[],
        owned_paths=[],
        receipts_dir="var/receipts",
        prompt_source="test",
    )


async def _run(name: str, payload) -> object:
    factory = IdFactory(FixtureClock(start=START), random.Random(12))
    with bind_correlation(CorrelationId.new(factory)):
        resolved = _registry().find(name, max_side_effect=SideEffect.READ, bot=_bot())
        return await resolved(payload)


async def test_trades_classifies_buy_and_sell() -> None:
    out = await _run("market.trades", TradesIn(mint=MINT))
    assert len(out.trades) == 2
    assert {t.side for t in out.trades} == {"buy", "sell"}
    assert out.buy_sell_ratio == Decimal(1)
    assert out.unique_wallets == 2
    assert out.meta.source == "solana_rpc"
    assert out.meta.freshness_s == 0.0


async def test_trades_since_ts_filters() -> None:
    out = await _run("market.trades", TradesIn(mint=MINT, since_ts=1060))
    assert len(out.trades) == 1
    assert out.trades[0].side == "sell"


async def test_ohlcv_buckets_trades() -> None:
    out = await _run("market.ohlcv", OhlcvIn(mint=MINT, interval_s=60))
    assert len(out.candles) == 2
    assert all(c.trades == 1 for c in out.candles)
    assert out.partial_last is True
    for candle in out.candles:
        assert candle.open == candle.close
        assert candle.high == candle.low == candle.open
    assert out.meta.source == "solana_rpc"


async def test_ohlcv_pure_bucketing_pins_math() -> None:
    from pumpgrok.tools.market.trades import Trade

    trades = [
        Trade(ts=61, side="buy", wallet=W1, sol_lamports=10, token_units=1_000_000, signature="a"),
        Trade(ts=62, side="buy", wallet=W1, sol_lamports=20, token_units=1_000_000, signature="b"),
    ]
    candles = build_ohlcv(trades, 60, 100)
    assert len(candles) == 1
    assert candles[0].ts == 60
    assert candles[0].trades == 2
    assert candles[0].volume_lamports == 30
    assert candles[0].low == Decimal("0.00000001")
    assert candles[0].high == Decimal("0.00000002")


async def test_liquidity_reports_reserves_and_impact() -> None:
    flat = await _run("market.liquidity", LiquidityIn(mint=MINT, curve_account=CURVE))
    assert flat.liquidity_lamports == VSOL
    assert flat.price_impact == Decimal(0)
    assert flat.order_to_liquidity_ratio == Decimal(0)
    assert flat.graduated is False
    sized = await _run(
        "market.liquidity", LiquidityIn(mint=MINT, curve_account=CURVE, order_size_lamports=VSOL)
    )
    assert sized.price_impact == Decimal("0.5")
    assert sized.order_to_liquidity_ratio == Decimal(1)
    assert sized.meta.source == "solana_rpc"


async def test_holders_snapshot_converts_to_ratios() -> None:
    out = await _run("market.holders_snapshot", HoldersSnapshotIn(mint=MINT))
    assert out.holder_count == 3
    assert [h.share for h in out.holders] == [Decimal("0.5"), Decimal("0.3"), Decimal("0.2")]
    assert out.top5_share == Decimal("1")
    assert out.creator is None
    assert out.creator_share == Decimal(0)
    assert out.meta.source == "solana_rpc"


def test_market_inputs_reject_unknown_fields() -> None:
    with pytest.raises(Exception):
        OhlcvIn(mint=MINT, venue_noise=1)  # type: ignore[call-arg]
    with pytest.raises(Exception):
        LiquidityIn(mint=MINT, curve_account=CURVE, venue_noise=1)  # type: ignore[call-arg]
    with pytest.raises(Exception):
        TradesIn(mint=MINT, venue_noise=1)  # type: ignore[call-arg]
    with pytest.raises(Exception):
        HoldersSnapshotIn(mint=MINT, venue_noise=1)  # type: ignore[call-arg]


async def test_market_upstream_failure_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32005}})

    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    client = httpx.AsyncClient(transport=transport)
    rpc = RpcClient(["https://a.invalid", "https://b.invalid"], client, FixtureClock(start=START),
                    rng=random.Random(5))
    reg, _ = build_registry(clock=FixtureClock(start=START), rng=random.Random(11))
    register_read_tools(reg, rpc)
    factory = IdFactory(FixtureClock(start=START), random.Random(12))
    with bind_correlation(CorrelationId.new(factory)):
        resolved = reg.find("market.trades", max_side_effect=SideEffect.READ, bot=_bot())
        with pytest.raises(DataStale):
            await resolved(TradesIn(mint=MINT))
