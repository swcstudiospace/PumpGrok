"""BLIND advisory for the SAFE-4/SAFE-8 holder pair (Phase 9 plan 09-05, UPG-05).

While no paid RPC provider is recorded (env PUMPGROK_PAID_RPC_PROVIDER empty
or unset), blind top10_concentration and blind deployer_history stay status
blind with their reasons, are listed as advisory in the verdict payload, and
do not KILL on their own. Every other required blind still KILLs, and with a
provider recorded the pair reverts to KILL on blind.
"""

from __future__ import annotations

import base64
import json
import random
import sys
import time
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import httpx
import pytest

from pumpgrok.core.bot import BotManifest, ToolGrant
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools import build_registry
from pumpgrok.tools.onchain.curve_layout import CURVE_ACCOUNT_SIZE, encode_curve_fixture
from pumpgrok.tools.onchain.rpc import RpcClient
from pumpgrok.tools.safety.provider import (
    PAID_RPC_PROVIDER_ENV_VAR,
    paid_rpc_provider_recorded,
)
from pumpgrok.tools.safety.score_report import ScoreReportIn, build_score_report_tool

START = 1469918176.385
MINT = "So11111111111111111111111111111111111111112"
CURVE = "8" * 44
CREATOR = "9" * 44

_NOW = int(time.time())


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


def _handler(
    *, holders_ok: bool = True, jsonparsed_ok: bool = True
) -> Callable[[httpx.Request], httpx.Response]:
    curve = _curve_b64()

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        method, params = body["method"], body["params"]
        if method == "getAccountInfo":
            if params[1].get("encoding") == "jsonParsed":
                if not jsonparsed_ok:
                    return httpx.Response(
                        200, json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32005}}
                    )
                result = {
                    "context": {"slot": 11},
                    "value": {
                        "data": {
                            "parsed": {
                                "info": {
                                    "mintAuthority": None,
                                    "freezeAuthority": None,
                                    "decimals": 6,
                                    "supply": "1000000000000",
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
            if not holders_ok:
                return httpx.Response(
                    200, json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32005}}
                )
            result = {
                "value": [
                    {"address": "A" * 44, "uiAmount": 50.0, "decimals": 6},
                    {"address": "B" * 44, "uiAmount": 30.0, "decimals": 6},
                    {"address": "C" * 44, "uiAmount": 20.0, "decimals": 6},
                ]
            }
        elif method == "getTokenSupply":
            result = {"context": {"slot": 9}, "value": {"amount": "1000000000000", "decimals": 6}}
        elif method == "getSignaturesForAddress":
            result = [{"signature": "d1", "slot": 1, "blockTime": _NOW - 100}]
        else:
            raise AssertionError(f"unexpected method {method}")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    return handler


def _run_with(handler, payload):
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    rpc = RpcClient(
        ["https://rpc.invalid"], client, FixtureClock(start=START), rng=random.Random(9)
    )
    reg, _ = build_registry(clock=FixtureClock(start=START), rng=random.Random(11))
    reg.register(build_score_report_tool(rpc))
    bot = BotManifest(
        id="bot-05-rug",
        display="rug",
        channel="DM",
        purpose="test seat",
        inputs=[],
        outputs=[],
        skills=[],
        allowed_tools=[ToolGrant(name="safety.score_report", side_effect=SideEffect.READ)],
        risk_budget={},
        forbidden=[],
        fail_safe="halt",
        schedule=[],
        escalation=[],
        owned_paths=[],
        receipts_dir="var/receipts",
        prompt_source="test",
    )
    return reg, bot


async def _call(reg, bot, payload):
    factory = IdFactory(FixtureClock(start=START), random.Random(12))
    with bind_correlation(CorrelationId.new(factory)):
        resolved = reg.find("safety.score_report", max_side_effect=SideEffect.READ, bot=bot)
        return await resolved(payload)


def _clear_in() -> ScoreReportIn:
    return ScoreReportIn(mint=MINT, curve_account=CURVE, creator=CREATOR)


def test_provider_signal_empty_means_none_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PAID_RPC_PROVIDER_ENV_VAR, raising=False)
    assert paid_rpc_provider_recorded() is False
    monkeypatch.setenv(PAID_RPC_PROVIDER_ENV_VAR, "   ")
    assert paid_rpc_provider_recorded() is False
    monkeypatch.setenv(PAID_RPC_PROVIDER_ENV_VAR, "provider-name")
    assert paid_rpc_provider_recorded() is True


async def test_holder_blind_is_advisory_without_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(PAID_RPC_PROVIDER_ENV_VAR, raising=False)
    reg, bot = _run_with(_handler(holders_ok=False), _clear_in())
    out = await _call(reg, bot, _clear_in())
    statuses = {c.id: c.status for c in out.checks}
    assert statuses["top10_concentration"] == "blind"
    row = next(c for c in out.checks if c.id == "top10_concentration")
    assert isinstance(row.reason, str) and row.reason
    assert "top10_concentration" in out.blind_checks
    assert "top10_concentration" in out.advisory_blind_checks
    assert out.verdict_recommendation != "KILL"


async def test_deployer_blind_is_advisory_without_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(PAID_RPC_PROVIDER_ENV_VAR, raising=False)
    payload = ScoreReportIn(mint=MINT, curve_account=CURVE)
    reg, bot = _run_with(_handler(), payload)
    out = await _call(reg, bot, payload)
    statuses = {c.id: c.status for c in out.checks}
    assert statuses["deployer_history"] == "blind"
    row = next(c for c in out.checks if c.id == "deployer_history")
    assert isinstance(row.reason, str) and row.reason
    assert "deployer_history" in out.blind_checks
    assert "deployer_history" in out.advisory_blind_checks
    assert out.verdict_recommendation != "KILL"


async def test_required_blind_still_kills_without_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(PAID_RPC_PROVIDER_ENV_VAR, raising=False)
    reg, bot = _run_with(_handler(jsonparsed_ok=False), _clear_in())
    out = await _call(reg, bot, _clear_in())
    statuses = {c.id: c.status for c in out.checks}
    assert statuses["mint_authority"] == "blind"
    assert "mint_authority" not in out.advisory_blind_checks
    assert out.verdict_recommendation == "KILL"


async def test_holder_blind_reverts_to_kill_with_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(PAID_RPC_PROVIDER_ENV_VAR, "provider-name")
    reg, bot = _run_with(_handler(holders_ok=False), _clear_in())
    out = await _call(reg, bot, _clear_in())
    statuses = {c.id: c.status for c in out.checks}
    assert statuses["top10_concentration"] == "blind"
    assert out.advisory_blind_checks == []
    assert out.verdict_recommendation == "KILL"


async def test_deployer_blind_reverts_to_kill_with_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(PAID_RPC_PROVIDER_ENV_VAR, "provider-name")
    payload = ScoreReportIn(mint=MINT, curve_account=CURVE)
    reg, bot = _run_with(_handler(), payload)
    out = await _call(reg, bot, payload)
    statuses = {c.id: c.status for c in out.checks}
    assert statuses["deployer_history"] == "blind"
    assert out.advisory_blind_checks == []
    assert out.verdict_recommendation == "KILL"
