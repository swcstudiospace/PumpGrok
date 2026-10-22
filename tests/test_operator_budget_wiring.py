"""Operator risk wiring: settings [risk]/[limits] reach the engine and adapter.

CR-01: build_operator_registry and build_adapter previously constructed the
RiskEngine with fresh RiskBudget()/EngineLimits() defaults and discarded
``settings``, so an operator-tuned [risk] or [limits] section had no effect.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest

import pumpgrok.tools as tools_mod
from pumpgrok.config.settings import load_settings
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution import build_adapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.tools import build_operator_registry

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip PUMPGROK_* so each test sets exactly what it needs."""
    for name in list(os.environ):
        if name.startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def test_limits_section_parses_from_env() -> None:
    """[limits] is a real Settings section: env overrides land on the model."""
    os.environ["PUMPGROK_RISK__MAX_OPEN_POSITIONS"] = "1"
    os.environ["PUMPGROK_LIMITS__MIN_TRADE_LAMPORTS"] = "20000000"
    settings = load_settings()
    assert settings.risk.max_open_positions == 1
    assert settings.limits.min_trade_lamports == 20_000_000


def test_build_adapter_uses_settings_budget_and_limits(tmp_path: Path) -> None:
    """The adapter carries the operator budget/limits, not fresh defaults."""
    clock = FixtureClock(1_769_900_000.0)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        engine = RiskEngine(
            store=store,
            budget=RiskBudget(),
            ids=IdFactory(clock, make_rng()),
            clock=clock,
        )
        settings = load_settings()
        settings.risk = RiskBudget(max_open_positions=1)
        settings.limits = EngineLimits(min_trade_lamports=99_000_000)
        adapter = build_adapter(
            settings,
            store=store,
            risk=engine,
            ids=IdFactory(clock, make_rng()),
            clock=clock,
            rng=make_rng(),
        )
        assert adapter._budget is settings.risk
        assert adapter._limits is settings.limits
    finally:
        store.close()


def test_build_adapter_falls_back_without_settings_attrs(tmp_path: Path) -> None:
    """Objects without risk/limits attributes still get working defaults."""
    clock = FixtureClock(1_769_900_000.0)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        engine = RiskEngine(
            store=store,
            budget=RiskBudget(),
            ids=IdFactory(clock, make_rng()),
            clock=clock,
        )
        adapter = build_adapter(
            object(),
            store=store,
            risk=engine,
            ids=IdFactory(clock, make_rng()),
            clock=clock,
            rng=make_rng(),
        )
        assert adapter._budget == RiskBudget()
        assert adapter._limits == EngineLimits()
    finally:
        store.close()


def test_operator_registry_threads_settings_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wired engine is built from settings.risk/settings.limits."""
    os.environ["PUMPGROK_RISK__MAX_OPEN_POSITIONS"] = "1"
    os.environ["PUMPGROK_LIMITS__MIN_TRADE_LAMPORTS"] = "20000000"
    settings = load_settings()

    seen: dict[str, Any] = {}
    real_engine = tools_mod.RiskEngine

    def _spy_engine(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return real_engine(**kwargs)

    monkeypatch.setattr(tools_mod, "RiskEngine", _spy_engine)
    reg, _manifests, client = build_operator_registry(
        data_dir=tmp_path / "desk",
        repo_root=ROOT,
        settings=settings,
        ledger_path=tmp_path / "ledger.sqlite",
        p_drop=0.0,
    )
    try:
        assert seen["budget"] is settings.risk
        assert seen["limits"] is settings.limits
        assert seen["budget"].max_open_positions == 1
        assert seen["limits"].min_trade_lamports == 20_000_000
        assert reg is not None
    finally:
        asyncio.run(client.aclose())
