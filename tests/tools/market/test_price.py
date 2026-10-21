"""Tracer: market.price over the RPC curve layout (Phase 3 plan 03-02, task 1).

[ASSUMED] fixture: hand-authored bonding-curve account bytes in the ASSUMED
layout (``curve_layout.encode_curve_fixture``); user confirmation pending.
MockTransport only; no live network.
"""

from __future__ import annotations

import base64
import json
import random
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import httpx
import pytest
from pydantic import ValidationError

from pumpgrok.core.bot import BotManifest, ToolGrant
from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import RetryPolicy
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools import build_registry
from pumpgrok.tools.market.price import PriceIn, build_price_tool
from pumpgrok.tools.onchain.curve_layout import CURVE_ACCOUNT_SIZE, encode_curve_fixture
from pumpgrok.tools.onchain.rpc import RpcClient

START = 1469918176.385
MINT = "So11111111111111111111111111111111111111112"
CURVE = "8" * 44

VSOL = 30_000_000_000
VTOK = 1_000_000_000_000_000
RSOL = 30_000_000_000
RTOK = 970_000_000_000_000
SUPPLY = 1_000_000_000_000_000


def _account_b64(complete: bool = False) -> str:
    raw = encode_curve_fixture(
        virtual_sol_reserves_lamports=VSOL,
        virtual_token_reserves_units=VTOK,
        real_sol_reserves_lamports=RSOL,
        real_token_reserves_units=RTOK,
        total_supply_units=SUPPLY,
        complete=complete,
    )
    assert len(raw) == CURVE_ACCOUNT_SIZE
    return base64.b64encode(raw).decode("ascii")


def _rpc_for(payload_b64: str | None, *, slot: int | None = 123) -> RpcClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        assert body["method"] == "getAccountInfo"
        if payload_b64 is None:
            result = {"context": {"slot": slot}, "value": None}
        else:
            result = {
                "context": {"slot": slot},
                "value": {
                    "data": [payload_b64, "base64"],
                    "executable": False,
                    "lamports": 1,
                    "owner": "CurveProgram11111111111111111111111111111111",
                    "rentEpoch": 1,
                },
            }
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    client = httpx.AsyncClient(transport=transport)
    return RpcClient(
        ["https://rpc.invalid"],
        client,
        FixtureClock(start=START),
        rng=random.Random(3),
        retry=RetryPolicy(attempts=3, base_s=0.01, max_s=0.02),
    )


def _scout() -> BotManifest:
    return BotManifest(
        id="bot-01-scout",
        display="scout",
        channel="DM",
        purpose="test seat",
        inputs=[],
        outputs=[],
        skills=[],
        allowed_tools=[ToolGrant(name="market.price", side_effect=SideEffect.READ)],
        risk_budget={},
        forbidden=[],
        fail_safe="halt",
        schedule=[],
        escalation=[],
        owned_paths=[],
        receipts_dir="var/receipts",
        prompt_source="test",
    )


def _resolve(reg) -> object:
    """Resolve under a bound correlation id (registry I4 requires one)."""
    factory = IdFactory(FixtureClock(start=START), random.Random(12))
    with bind_correlation(CorrelationId.new(factory)):
        return reg.find("market.price", max_side_effect=SideEffect.READ, bot=_scout())


async def _call(resolved: object, payload: PriceIn) -> object:
    factory = IdFactory(FixtureClock(start=START), random.Random(13))
    with bind_correlation(CorrelationId.new(factory)):
        return await resolved(payload)  # type: ignore[operator]


async def test_price_resolves_via_registry_and_returns_typed_output() -> None:
    reg, _ = build_registry(clock=FixtureClock(start=START), rng=random.Random(11))
    reg.register(build_price_tool(_rpc_for(_account_b64())))
    resolved = _resolve(reg)
    out = await _call(resolved, PriceIn(mint=MINT, curve_account=CURVE))
    assert out.price == Decimal("0.00000003")
    assert out.source == "curve"
    assert Decimal(0) < out.curve_progress < Decimal(1)
    assert out.market_cap_lamports == VSOL
    assert out.graduated is False
    assert out.context_slot == 123
    assert out.meta.source == "solana_rpc"
    assert out.meta.freshness_s == 0.0


async def test_price_malformed_account_yields_typed_error() -> None:
    reg, _ = build_registry(clock=FixtureClock(start=START), rng=random.Random(11))
    short = base64.b64encode(b"\x00" * 7).decode("ascii")
    reg.register(build_price_tool(_rpc_for(short)))
    resolved = _resolve(reg)
    with pytest.raises(DataStale):
        await _call(resolved, PriceIn(mint=MINT, curve_account=CURVE))


async def test_price_missing_account_yields_typed_error() -> None:
    reg, _ = build_registry(clock=FixtureClock(start=START), rng=random.Random(11))
    reg.register(build_price_tool(_rpc_for(None)))
    resolved = _resolve(reg)
    with pytest.raises(DataStale):
        await _call(resolved, PriceIn(mint=MINT, curve_account=CURVE))


def test_price_input_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PriceIn(mint=MINT, curve_account=CURVE, venue_noise=1)  # type: ignore[call-arg]


def test_price_has_no_rest_or_quote_fallback() -> None:
    root = Path(__file__).resolve().parents[3] / "src" / "pumpgrok" / "tools"
    for rel in ("market/price.py", "onchain/curve_layout.py"):
        text = (root / rel).read_text(encoding="utf-8")
        for marker in ("frontend-api", "jup.ag", "lite-api", "JUPITER", "httpx"):
            assert marker not in text, f"{rel} must not reference {marker}"
