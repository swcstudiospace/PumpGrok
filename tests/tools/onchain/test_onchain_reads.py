"""Onchain READ tools over RPC fixtures (Phase 3 plan 03-02, task 2 RED).

Covers onchain.token_metadata, onchain.authorities, onchain.lp_status,
onchain.top_holders, onchain.deployer_history, onchain.large_transfers and
onchain.priority_fee: every output carries meta.source and
meta.freshness_s, unknown input fields are rejected, and no test touches
live network (single MockTransport handler only).
"""

from __future__ import annotations

import base64
import json
import random
import sys
import time
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
from pumpgrok.tools.onchain.authorities_tool import AuthoritiesIn
from pumpgrok.tools.onchain.curve_layout import CURVE_ACCOUNT_SIZE, encode_curve_fixture
from pumpgrok.tools.onchain.deployer_history import DeployerHistoryIn
from pumpgrok.tools.onchain.large_transfers import LargeTransfersIn
from pumpgrok.tools.onchain.lp_status import LpStatusIn
from pumpgrok.tools.onchain.priority_fee_tool import PriorityFeeIn
from pumpgrok.tools.onchain.rpc import RpcClient
from pumpgrok.tools.onchain.token_metadata import TokenMetadataIn
from pumpgrok.tools.onchain.top_holders import TopHoldersIn

START = 1469918176.385
MINT = "So11111111111111111111111111111111111111112"
CURVE = "8" * 44
CREATOR = "9" * 44
WALLET = "7" * 44
R1 = "6" * 44
FREEZE = "F" * 44

SUPPLY = 100_000_000

ALL_NAMES = [
    "market.price", "market.ohlcv", "market.liquidity", "market.trades",
    "market.holders_snapshot", "onchain.token_metadata", "onchain.authorities",
    "onchain.lp_status", "onchain.top_holders", "onchain.deployer_history",
    "onchain.large_transfers", "onchain.priority_fee",
]


def _curve_b64() -> str:
    raw = encode_curve_fixture(
        virtual_sol_reserves_lamports=30_000_000_000,
        virtual_token_reserves_units=1_000_000_000_000_000,
        real_sol_reserves_lamports=30_000_000_000,
        real_token_reserves_units=970_000_000_000_000,
        total_supply_units=1_000_000_000_000_000,
        complete=False,
    )
    assert len(raw) == CURVE_ACCOUNT_SIZE
    return base64.b64encode(raw).decode("ascii")


_NOW = int(time.time())

_TRANSFER_TX = {
    "blockTime": _NOW - 50,
    "meta": {
        "err": None,
        "preBalances": [1000, 0],
        "postBalances": [1010, 0],
        "preTokenBalances": [
            {"accountIndex": 0, "mint": MINT, "uiTokenAmount": {"amount": "10000000000000"}},
        ],
        "postTokenBalances": [
            {"accountIndex": 0, "mint": MINT, "uiTokenAmount": {"amount": "0"}},
            {"accountIndex": 1, "mint": MINT, "uiTokenAmount": {"amount": "10000000000000"}},
        ],
    },
    "transaction": {"message": {"accountKeys": [{"pubkey": WALLET}, {"pubkey": R1}]}},
}


def _rpc() -> RpcClient:
    curve = _curve_b64()

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        method, params = body["method"], body["params"]
        if method == "getAccountInfo":
            if params[1].get("encoding") == "jsonParsed":
                result = {
                    "context": {"slot": 11},
                    "value": {
                        "data": {
                            "parsed": {
                                "info": {
                                    "mintAuthority": None,
                                    "freezeAuthority": FREEZE,
                                    "decimals": 6,
                                    "supply": str(SUPPLY),
                                    "isInitialized": True,
                                    "extensions": [],
                                }
                            }
                        }
                    },
                }
            else:
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
        elif method == "getTokenLargestAccounts":
            result = {
                "value": [
                    {"address": "A" * 44, "uiAmount": 50.0, "decimals": 6},
                    {"address": "B" * 44, "uiAmount": 30.0, "decimals": 6},
                    {"address": "C" * 44, "uiAmount": 20.0, "decimals": 6},
                ]
            }
        elif method == "getTokenSupply":
            result = {"context": {"slot": 9}, "value": {"amount": str(SUPPLY), "decimals": 6}}
        elif method == "getSignaturesForAddress":
            if params[0] == CREATOR:
                result = [
                    {"signature": "d1", "slot": 1, "blockTime": _NOW - 100},
                    {"signature": "d2", "slot": 2, "blockTime": _NOW - 200},
                ]
            elif params[0] == WALLET:
                result = [{"signature": "t1", "slot": 3, "blockTime": _NOW - 50}]
            else:
                result = []
        elif method == "getTransaction":
            result = _TRANSFER_TX
        elif method == "getRecentPrioritizationFees":
            result = [
                {"slot": 1, "prioritizationFee": 100},
                {"slot": 2, "prioritizationFee": 200},
                {"slot": 3, "prioritizationFee": 300},
            ]
        else:
            raise AssertionError(f"unexpected method {method}")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    client = httpx.AsyncClient(transport=transport)
    return RpcClient(
        ["https://rpc.invalid"],
        client,
        FixtureClock(start=START),
        rng=random.Random(6),
    )


def _registry():
    reg, _ = build_registry(clock=FixtureClock(start=START), rng=random.Random(11))
    register_read_tools(reg, _rpc())
    return reg


def _bot(tool_names: list[str] | None = None) -> BotManifest:
    names = tool_names if tool_names is not None else ALL_NAMES
    return BotManifest(
        id="bot-05-rug",
        display="rug",
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


async def _run(name: str, payload, bot: BotManifest | None = None) -> object:
    factory = IdFactory(FixtureClock(start=START), random.Random(12))
    with bind_correlation(CorrelationId.new(factory)):
        resolved = _registry().find(name, max_side_effect=SideEffect.READ, bot=bot or _bot())
        return await resolved(payload)


async def test_all_twelve_specs_register_with_dotted_ids() -> None:
    reg = _registry()
    assert set(ALL_NAMES) <= set(reg.names())
    for name in ALL_NAMES:
        spec = reg.spec(name)
        assert spec.side_effect is SideEffect.READ
        assert spec.retry.attempts == 3
        assert spec.rate_limit_key == "solana_rpc"
        assert spec.timeout_s > 0


async def test_token_metadata_wraps_mint_account() -> None:
    out = await _run("onchain.token_metadata", TokenMetadataIn(mint=MINT))
    assert out.decimals == 6
    assert out.supply == str(SUPPLY)
    assert out.is_initialized is True
    assert out.program == "spl-token"
    assert out.name is None
    assert out.meta.source == "solana_rpc"
    assert out.meta.freshness_s == 0.0


async def test_authorities_flags_freeze_only() -> None:
    out = await _run("onchain.authorities", AuthoritiesIn(mint=MINT))
    assert out.has_mint_authority is False
    assert out.has_freeze_authority is True
    assert out.freeze_authority == FREEZE
    assert out.slot is None


async def test_lp_status_reads_curve_account() -> None:
    out = await _run("onchain.lp_status", LpStatusIn(mint=MINT, curve_account=CURVE))
    assert out.stage == "bonding_curve"
    assert out.curve_complete is False
    assert out.checked == ["curve_account"]
    assert out.lp_mint is None


async def test_top_holders_shares_against_supply() -> None:
    out = await _run("onchain.top_holders", TopHoldersIn(mint=MINT))
    assert out.supply_units == SUPPLY
    assert out.top1_share == Decimal("0.5")
    assert out.top5_share == Decimal("1")
    assert out.top10_share == Decimal("1")
    assert all(h.owner is None for h in out.holders)


async def test_top_holders_excludes_curve_accounts() -> None:
    out = await _run("onchain.top_holders", TopHoldersIn(mint=MINT, exclude=["A" * 44]))
    assert out.excluded == ["A" * 44]
    assert out.top1_share == Decimal("0.3")
    assert all(h.address != "A" * 44 for h in out.holders)


async def test_deployer_history_counts_window() -> None:
    out = await _run("onchain.deployer_history", DeployerHistoryIn(creator=CREATOR))
    assert out.tokens_seen == 2
    assert out.recent_signatures == ["d1", "d2"]
    assert out.is_known_bad is False
    assert out.first_seen_at is not None


async def test_large_transfers_flags_whale_sell() -> None:
    out = await _run("onchain.large_transfers", LargeTransfersIn(mint=MINT, wallets=[WALLET]))
    assert len(out.transfers) == 1
    transfer = out.transfers[0]
    assert transfer.kind == "sell"
    assert transfer.share == Decimal("0.01")
    assert transfer.amount_units == 10_000_000_000_000


async def test_large_transfers_default_watch_set_is_empty_result() -> None:
    out = await _run("onchain.large_transfers", LargeTransfersIn(mint=MINT))
    assert out.transfers == []


async def test_priority_fee_caps_and_flags() -> None:
    out = await _run("onchain.priority_fee", PriorityFeeIn())
    assert out.samples == 3
    assert out.median == 200
    assert out.percentile_fee == 200
    assert out.recommended_micro_lamports == 240
    assert out.capped is False
    capped = await _run("onchain.priority_fee", PriorityFeeIn(max_micro_lamports=100))
    assert capped.recommended_micro_lamports == 100
    assert capped.capped is True


def test_onchain_inputs_reject_unknown_fields() -> None:
    with pytest.raises(Exception):
        TokenMetadataIn(mint=MINT, venue_noise=1)  # type: ignore[call-arg]
    with pytest.raises(Exception):
        AuthoritiesIn(mint=MINT, venue_noise=1)  # type: ignore[call-arg]
    with pytest.raises(Exception):
        LpStatusIn(mint=MINT, curve_account=CURVE, venue_noise=1)  # type: ignore[call-arg]
    with pytest.raises(Exception):
        TopHoldersIn(mint=MINT, venue_noise=1)  # type: ignore[call-arg]
    with pytest.raises(Exception):
        DeployerHistoryIn(creator=CREATOR, venue_noise=1)  # type: ignore[call-arg]
    with pytest.raises(Exception):
        LargeTransfersIn(mint=MINT, venue_noise=1)  # type: ignore[call-arg]
    with pytest.raises(Exception):
        PriorityFeeIn(venue_noise=1)  # type: ignore[call-arg]


async def test_onchain_upstream_failure_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32005}})

    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    client = httpx.AsyncClient(transport=transport)
    rpc = RpcClient(["https://a.invalid"], client, FixtureClock(start=START), rng=random.Random(6))
    reg, _ = build_registry(clock=FixtureClock(start=START), rng=random.Random(11))
    register_read_tools(reg, rpc)
    factory = IdFactory(FixtureClock(start=START), random.Random(12))
    with bind_correlation(CorrelationId.new(factory)):
        resolved = reg.find("onchain.authorities", max_side_effect=SideEffect.READ, bot=_bot())
        with pytest.raises(DataStale):
            await resolved(AuthoritiesIn(mint=MINT))
