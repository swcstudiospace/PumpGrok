"""safety.score_report over RPC fixtures (Phase 3 plan 03-02, task 3).

Pins BLIND-not-exception semantics, config-driven thresholds, the 45s
spec, and the CLEAR/CONDITIONAL/KILL ladder. MockTransport only.
"""

from __future__ import annotations

import base64
import json
import random
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import httpx

from pumpgrok.core.bot import BotManifest, ToolGrant
from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools import build_registry
from pumpgrok.tools.onchain.curve_layout import CURVE_ACCOUNT_SIZE, encode_curve_fixture
from pumpgrok.tools.onchain.rpc import RpcClient
from pumpgrok.tools.safety.score_report import ScoreReportIn, build_score_report_tool

START = 1469918176.385
MINT = "So11111111111111111111111111111111111111112"
CURVE = "8" * 44
CREATOR = "9" * 44
FREEZE = "F" * 44

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


def _handler(*, freeze_live: bool, supply: str, holders_ok: bool):
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
                                    "freezeAuthority": FREEZE if freeze_live else None,
                                    "decimals": 6,
                                    "supply": supply,
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
            result = {"context": {"slot": 9}, "value": {"amount": supply, "decimals": 6}}
        elif method == "getSignaturesForAddress":
            result = [{"signature": "d1", "slot": 1, "blockTime": _NOW - 100}]
        else:
            raise AssertionError(f"unexpected method {method}")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    return handler


def _run_with(handler, payload: ScoreReportIn):
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
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


async def _call(reg, bot, payload: ScoreReportIn) -> object:
    factory = IdFactory(FixtureClock(start=START), random.Random(12))
    with bind_correlation(CorrelationId.new(factory)):
        resolved = reg.find("safety.score_report", max_side_effect=SideEffect.READ, bot=bot)
        return await resolved(payload)


def _clear_in() -> ScoreReportIn:
    return ScoreReportIn(mint=MINT, curve_account=CURVE, creator=CREATOR)


async def test_clear_report_on_clean_data() -> None:
    reg, bot = _run_with(
        _handler(freeze_live=False, supply="1000000000000", holders_ok=True), _clear_in()
    )
    out = await _call(reg, bot, _clear_in())
    assert out.score == 100
    assert out.verdict_recommendation == "CLEAR"
    assert out.hard_veto is False
    assert out.blind_checks == ["transfer_tax", "honeypot", "bundler_cluster"]
    assert out.meta.source == "solana_rpc"
    assert out.meta.freshness_s == 0.0
    assert out.thresholds_used["kill_below_score"] == 40.0
    assert all(isinstance(c.reason, str) and c.reason for c in out.checks)


async def test_conditional_on_concentration_and_freeze() -> None:
    reg, bot = _run_with(
        _handler(freeze_live=True, supply="200000000", holders_ok=True), _clear_in()
    )
    out = await _call(reg, bot, _clear_in())
    assert out.score == 50
    assert out.verdict_recommendation == "CONDITIONAL"
    assert out.hard_veto is False
    statuses = {c.id: c.status for c in out.checks}
    assert statuses["freeze_authority"] == "fail"
    assert statuses["top10_concentration"] == "fail"


async def test_kill_on_top5_hard_veto() -> None:
    reg, bot = _run_with(
        _handler(freeze_live=False, supply="100000000", holders_ok=True), _clear_in()
    )
    out = await _call(reg, bot, _clear_in())
    assert out.hard_veto is True
    assert out.verdict_recommendation == "KILL"


async def test_blind_never_raises_and_forces_kill() -> None:
    reg, bot = _run_with(
        _handler(freeze_live=False, supply="1000000000000", holders_ok=False), _clear_in()
    )
    out = await _call(reg, bot, _clear_in())
    statuses = {c.id: c.status for c in out.checks}
    assert statuses["top10_concentration"] == "blind"
    assert "top10_concentration" in out.blind_checks
    assert out.verdict_recommendation == "KILL"


async def test_unknown_check_and_threshold_ids_are_refused() -> None:
    reg, bot = _run_with(
        _handler(freeze_live=False, supply="1000000000000", holders_ok=True), _clear_in()
    )
    with pytest.raises(DataStale):
        await _call(reg, bot, ScoreReportIn(mint=MINT, curve_account=CURVE, checks=["nope"]))
    with pytest.raises(DataStale):
        await _call(
            reg, bot, ScoreReportIn(mint=MINT, curve_account=CURVE, thresholds={"nope": 1.0})
        )


async def test_threshold_override_moves_verdict() -> None:
    reg, bot = _run_with(
        _handler(freeze_live=True, supply="1000000000000", holders_ok=True), _clear_in()
    )
    base = await _call(reg, bot, _clear_in())
    assert base.score == 75
    assert base.verdict_recommendation == "CLEAR"
    over = await _call(
        reg,
        bot,
        ScoreReportIn(
            mint=MINT, curve_account=CURVE, creator=CREATOR, thresholds={"kill_below_score": 95.0}
        ),
    )
    assert over.score == base.score
    assert over.verdict_recommendation == "KILL"


async def test_checks_subset_limits_runnable() -> None:
    reg, bot = _run_with(
        _handler(freeze_live=False, supply="1000000000000", holders_ok=True), _clear_in()
    )
    out = await _call(
        reg,
        bot,
        ScoreReportIn(mint=MINT, curve_account=CURVE, creator=CREATOR, checks=["mint_authority"]),
    )
    assert [c.id for c in out.checks] == ["mint_authority"]


def test_score_spec_contract() -> None:
    from pumpgrok.tools.safety.score_report import SCORE_SPEC

    assert SCORE_SPEC.name == "safety.score_report"
    assert SCORE_SPEC.timeout_s == 45.0
    assert SCORE_SPEC.retry.attempts == 1
    assert SCORE_SPEC.rate_limit_key == "solana_rpc"


def test_score_input_rejects_unknown_fields() -> None:
    with pytest.raises(Exception):
        ScoreReportIn(mint=MINT, curve_account=CURVE, venue_noise=1)  # type: ignore[call-arg]
