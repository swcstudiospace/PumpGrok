"""Regression: operator wiring must use loaded config (review findings 22, 23, 3, 19).

22: the configured RPC api_key reaches the shared RpcClient.
23: the configured safety thresholds reach safety.score_report.
3:  caller threshold overrides merge over the configured thresholds, not replace them.
19: configured notify.allowlist destinations receive alerts through the real senders.
"""

from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

import pumpgrok.tools as tools_mod
from pumpgrok.config.settings import SafetyThresholds, load_settings
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools import build_operator_registry
from pumpgrok.tools.notify.alert import AlertIn
from pumpgrok.tools.onchain.rpc import RpcClient
from pumpgrok.tools.safety.score_report import (
    _HIGHER_IS_STRICTER,
    _LOWER_IS_STRICTER,
    ScoreReportIn,
    resolve_thresholds,
    run_score_report,
)

ROOT = Path(__file__).resolve().parents[2]
START = 1469918176.385
MINT = "So11111111111111111111111111111111111111112"
CURVE = "8" * 44


def _build(tmp_path: Path, settings: Any) -> None:
    _reg, _manifests, client = build_operator_registry(
        data_dir=tmp_path / "desk",
        repo_root=ROOT,
        settings=settings,
        ledger_path=tmp_path / "ledger.sqlite",
        p_drop=0.0,
    )
    asyncio.run(client.aclose())


def test_operator_registry_forwards_rpc_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PUMPGROK_RPC__API_KEY", "paid-key-123")
    settings = load_settings()
    seen: dict[str, Any] = {}
    real_rpc = tools_mod.RpcClient

    class _SpyRpc(real_rpc):  # type: ignore[valid-type,misc]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            seen.update(kwargs)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(tools_mod, "RpcClient", _SpyRpc)
    _build(tmp_path, settings)
    assert isinstance(seen["api_key"], SecretStr)
    assert seen["api_key"].get_secret_value() == "paid-key-123"


def test_operator_registry_forwards_safety_thresholds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PUMPGROK_SAFETY__THRESHOLDS__TOP10_CONCENTRATION_FAIL_PCT", "7.5")
    monkeypatch.setenv("PUMPGROK_SAFETY__THRESHOLDS__KILL_BELOW_SCORE", "55")
    settings = load_settings()
    seen: dict[str, Any] = {}
    real_factory = tools_mod.build_score_report_tool

    def _spy_factory(rpc: Any, thresholds: Any = None) -> Any:
        seen["thresholds"] = thresholds
        return real_factory(rpc, thresholds)

    monkeypatch.setattr(tools_mod, "build_score_report_tool", _spy_factory)
    _build(tmp_path, settings)
    thresholds = seen["thresholds"]
    assert thresholds is not None
    assert thresholds.top10_concentration_fail_pct == 7.5
    assert thresholds.kill_below_score == 55.0
    assert thresholds == settings.safety.thresholds


async def test_caller_override_merges_over_configured_thresholds() -> None:
    configured = SafetyThresholds(kill_below_score=30.0, top10_concentration_fail_pct=7.5)
    client = httpx.AsyncClient()
    rpc = RpcClient(["https://rpc.invalid"], client, FixtureClock(start=START), random.Random(3))
    try:
        out = await run_score_report(
            ScoreReportIn(
                mint=MINT, curve_account=CURVE, checks=[], thresholds={"kill_below_score": 95.0}
            ),
            rpc,
            thresholds=configured,
        )
    finally:
        await client.aclose()
    used = out["thresholds_used"]
    assert used["kill_below_score"] == 95.0  # the caller's stricter override applies
    assert used["top10_concentration_fail_pct"] == 7.5  # untouched keys keep configured values


async def test_configured_webhook_receives_alert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://alerts.example.test/hook"
    monkeypatch.setenv("PUMPGROK_NOTIFY__ALLOWLIST", json.dumps([url]))
    settings = load_settings()
    posted: list[httpx.Request] = []

    async def _fake_handle(
        self: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        posted.append(request)
        return httpx.Response(200, request=request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _fake_handle)
    reg, manifests, client = build_operator_registry(
        data_dir=tmp_path / "desk",
        repo_root=ROOT,
        settings=settings,
        clock=FixtureClock(start=START),
        ledger_path=tmp_path / "ledger.sqlite",
        p_drop=0.0,
    )
    try:
        factory = IdFactory(FixtureClock(start=START), random.Random(5))
        with bind_correlation(CorrelationId.new(factory)):
            alert = reg.find(
                "notify.alert",
                max_side_effect=SideEffect.PAPER_WRITE,
                bot=manifests["bot-09-journal"],
            )
            out = await alert(AlertIn(severity="critical", kind="escalation", text="rug flagged"))
    finally:
        await client.aclose()
    delivered = {d["sink"]: d for d in out.delivered}
    assert delivered[url]["ok"] is True
    assert [str(r.url) for r in posted] == [url]


CONFIGURED = SafetyThresholds(
    kill_below_score=30.0,
    conditional_below_score=60.0,
    liquidity_multiple_min=10.0,
    liquidity_multiple_recommended=20.0,
    lp_lock_min_days=180.0,
    top10_concentration_warn_pct=15.0,
    top10_concentration_fail_pct=25.0,
    transfer_tax_warn_pct=5.0,
    transfer_tax_hard_fail_pct=10.0,
    creator_share_veto=0.25,
    top5_share_veto=0.80,
)


def test_direction_table_covers_every_threshold_field() -> None:
    fields = set(SafetyThresholds.model_fields)
    assert fields == _HIGHER_IS_STRICTER | _LOWER_IS_STRICTER
    assert not _HIGHER_IS_STRICTER & _LOWER_IS_STRICTER


def test_stricter_caller_value_wins_in_both_directions() -> None:
    # Higher is stricter for a score floor: the caller's 45 beats the configured 30.
    # Lower is stricter for a concentration ceiling: the caller's 12 beats the configured 15.
    effective = resolve_thresholds(
        {"kill_below_score": 45.0, "top10_concentration_warn_pct": 12.0}, CONFIGURED
    )
    assert effective.kill_below_score == 45.0
    assert effective.top10_concentration_warn_pct == 12.0


def test_looser_caller_value_is_ignored() -> None:
    effective = resolve_thresholds(
        {
            "kill_below_score": 20.0,  # looser floor
            "liquidity_multiple_min": 2.0,  # looser floor
            "top10_concentration_fail_pct": 50.0,  # looser ceiling
            "transfer_tax_hard_fail_pct": 99.0,  # looser ceiling
        },
        CONFIGURED,
    )
    assert effective.kill_below_score == 30.0
    assert effective.liquidity_multiple_min == 10.0
    assert effective.top10_concentration_fail_pct == 25.0
    assert effective.transfer_tax_hard_fail_pct == 10.0


def test_unset_caller_value_keeps_configured_value() -> None:
    assert resolve_thresholds(None, CONFIGURED) == CONFIGURED
    assert resolve_thresholds({}, CONFIGURED) == CONFIGURED
    effective = resolve_thresholds({"kill_below_score": 45.0}, CONFIGURED)
    assert effective.model_dump() == {**CONFIGURED.model_dump(), "kill_below_score": 45.0}


def test_caller_value_without_configured_base_is_accepted() -> None:
    assert resolve_thresholds({"kill_below_score": 20.0}).kill_below_score == 20.0


async def test_run_score_report_uses_stricter_configured_kill_floor() -> None:
    # Reproduction for finding 3: a caller asks for a stricter kill floor than configured.
    client = httpx.AsyncClient()
    rpc = RpcClient(["https://rpc.invalid"], client, FixtureClock(start=START), random.Random(3))
    try:
        out = await run_score_report(
            ScoreReportIn(
                mint=MINT, curve_account=CURVE, checks=[], thresholds={"kill_below_score": 95.0}
            ),
            rpc,
            thresholds=CONFIGURED,
        )
    finally:
        await client.aclose()
    assert out["thresholds_used"]["kill_below_score"] == 95.0
