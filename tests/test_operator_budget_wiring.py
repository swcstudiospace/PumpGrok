"""Operator risk wiring: settings [risk]/[limits] reach the engine and adapter.

CR-01: build_operator_registry and build_adapter previously constructed the
RiskEngine with fresh RiskBudget()/EngineLimits() defaults and discarded
``settings``, so an operator-tuned [risk] or [limits] section had no effect.
"""

from __future__ import annotations

import asyncio
import os
import random
from collections.abc import Coroutine
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import pumpgrok.tools as tools_mod
from pumpgrok.config.settings import load_settings
from pumpgrok.core.adapter import Fill, OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution import build_adapter
from pumpgrok.execution.curve_math import buy_out
from pumpgrok.execution.fees import FeeModel
from pumpgrok.execution.paper_adapter import CurveSnapshot, OrderRejectedError
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


def test_limits_section_parses_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """[limits] is a real Settings section: env overrides land on the model."""
    monkeypatch.setenv("PUMPGROK_RISK__MAX_OPEN_POSITIONS", "1")
    monkeypatch.setenv("PUMPGROK_LIMITS__MIN_TRADE_LAMPORTS", "20000000")
    settings = load_settings()
    assert settings.risk.max_open_positions == 1
    assert settings.limits.min_trade_lamports == 20_000_000


S0 = 42_000_000_000
T0 = 766_428_571_428_571
EQUITY = 10_000_000_000
SIZE = 200_000_000
MINT = "So11111111111111111111111111111111111111112"
TICKET = "SOL-20260201-001"
# A 200M buy moves the curve about 50 bps: above a 20 bps ceiling, below the 100 bps request.
MOVED_S1 = S0 + S0 // 400
MOVED_T1 = S0 * T0 // MOVED_S1


class _Curves:
    """Scripted curve reads: the first read prices the decision, later reads confirm."""

    def __init__(self, reads: list[CurveSnapshot]) -> None:
        self._reads = list(reads)

    async def curve(self, mint: str) -> CurveSnapshot | None:
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


def _snap(s: int, t: int) -> CurveSnapshot:
    return CurveSnapshot(mint=MINT, s_lamports=s, t_units=t, complete=False)


async def _drive(coro: Coroutine[Any, Any, Fill], clock: FixtureClock) -> Fill:
    task = asyncio.create_task(coro)
    for _ in range(400):
        if task.done():
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    return await task


def _buy_outcome(
    tmp_path: Path, settings: object
) -> tuple[list[dict[str, Any]], Fill | OrderRejectedError]:
    """Run one 200M BUY requesting 100 bps through an adapter built from ``settings``."""
    clock = FixtureClock(1_769_900_000.0)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    ids = IdFactory(clock, make_rng(7))
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(7)),
        clock=clock,
        autonomy="autonomous-paper",
        get_reserves=lambda _mint: (S0, T0),
    )
    adapter = build_adapter(
        settings,
        store=store,
        risk=engine,
        ids=ids,
        clock=clock,
        rng=make_rng(7),
        price_source=_Curves([_snap(S0, T0), _snap(MOVED_S1, MOVED_T1)]),
        p_drop=0.0,
    )
    request = OrderRequest(
        ticket_id=TICKET,
        mint=MINT,
        side=Side.BUY,
        decision_id=ids.ulid(),
        size_lamports=SIZE,
        max_slippage_bps=100,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )
    outcome: Fill | OrderRejectedError
    try:
        outcome = asyncio.run(
            _drive(adapter.place(request, seat="bot-04-sniper", correlation_id="test"), clock)
        )
    except OrderRejectedError as exc:
        outcome = exc
    try:
        rows = store.read(limit=None)
    finally:
        store.close()
    return rows, outcome


def test_operator_slippage_limit_clamps_request_in_ledger(tmp_path: Path) -> None:
    """A [limits] ceiling below the 100 bps request refuses the fill at the clamped threshold."""
    settings = SimpleNamespace(risk=RiskBudget(), limits=EngineLimits(max_slippage_bps=20))
    rows, outcome = _buy_outcome(tmp_path, settings)
    assert isinstance(outcome, OrderRejectedError)
    assert outcome.reason == "slippage_exceeded"
    assert not [row for row in rows if row["type"] == "FillRecorded"]
    (reject,) = [row for row in rows if row["type"] == "OrderRejected"]
    payload = reject["payload"]
    assert isinstance(payload, dict)
    quote_out = buy_out(S0, T0, SIZE - FeeModel().venue_fee(SIZE))
    assert payload["other_amount_threshold"] == quote_out * (10_000 - 20) // 10_000


def test_build_adapter_without_settings_uses_default_limit(tmp_path: Path) -> None:
    """Objects without risk/limits attributes get defaults; the 300 bps ceiling admits the move."""
    rows, outcome = _buy_outcome(tmp_path, object())
    assert isinstance(outcome, Fill)
    assert outcome.status.value == "filled"
    assert [row for row in rows if row["type"] == "FillRecorded"]


def test_operator_registry_threads_settings_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wired engine is built from settings.risk/settings.limits."""
    monkeypatch.setenv("PUMPGROK_RISK__MAX_OPEN_POSITIONS", "1")
    monkeypatch.setenv("PUMPGROK_LIMITS__MIN_TRADE_LAMPORTS", "20000000")
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
        assert seen["budget"].max_open_positions == 1
        assert seen["limits"].min_trade_lamports == 20_000_000
        assert reg is not None
    finally:
        asyncio.run(client.aclose())
