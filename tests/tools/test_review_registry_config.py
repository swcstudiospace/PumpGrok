"""Regression: operator wiring must use the loaded RPC key and safety thresholds.

Review findings 22 (RPC api_key dropped) and 23 (safety thresholds ignored).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

import pumpgrok.tools as tools_mod
from pumpgrok.config.settings import load_settings
from pumpgrok.tools import build_operator_registry

ROOT = Path(__file__).resolve().parents[2]


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
