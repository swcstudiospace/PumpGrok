"""No live adapter is registered or enabled (LIV-01, D-03).

Three facts: build_adapter returns a PaperAdapter instance and never a live
adapter; the execution package exports no live adapter symbol and no registry
maps a name to a live implementation; the gate reports adapter_registered
unmet with the reason naming that no implementation ships. The test fails if
any future change registers a live adapter. ASCII only, no network use.
"""

from __future__ import annotations

import types
from pathlib import Path

import pumpgrok.execution as execution
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution import PaperAdapter, build_adapter
from pumpgrok.execution.live.live_adapter import LiveAdapterStub
from pumpgrok.execution.live.live_gate import LiveGate
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine

EPOCH_START = 1767225600.0  # 2026-01-01T00:00:00Z
NOW = "2026-10-20T00:00:00Z"


def _adapter(tmp_path: Path) -> PaperAdapter:
    """One factory-built adapter over a scratch ledger and engine."""
    clock = FixtureClock(start=EPOCH_START)
    ids = IdFactory(clock, make_rng())
    store = LedgerStore(tmp_path / "ledger.sqlite")
    risk = RiskEngine(store=store, budget=RiskBudget(), ids=ids, clock=clock)
    return build_adapter(object(), store=store, risk=risk, ids=ids, clock=clock, rng=make_rng())


def test_build_adapter_returns_paper_adapter_only(tmp_path: Path) -> None:
    """LIV-01: the factory builds PaperAdapter, never a live adapter."""
    adapter = _adapter(tmp_path)
    assert isinstance(adapter, PaperAdapter)
    assert not isinstance(adapter, LiveAdapterStub)
    assert type(adapter).__name__ == "PaperAdapter"


def test_execution_package_exports_no_live_adapter() -> None:
    """LIV-01: no live symbol and no registry entry in the execution package."""
    assert getattr(execution, "LiveAdapterStub", None) is None
    assert getattr(execution, "LiveAdapter", None) is None
    assert isinstance(execution.live, types.ModuleType)
    assert execution.live.__name__ == "pumpgrok.execution.live"
    for name in execution.__all__:
        assert "live" not in name.lower()
    for name in dir(execution):
        if name != "live":
            assert "live" not in name.lower()
    registries = [value for value in vars(execution).values() if isinstance(value, dict)]
    for registry in registries:
        for key, value in registry.items():
            assert "live" not in str(key).lower()
            assert value is not LiveAdapterStub


def test_gate_reports_adapter_unmet_with_reason(tmp_path: Path) -> None:
    """LIV-01: precondition 8 stays unmet naming the missing implementation."""
    gate = LiveGate(mode="live", environ={"PUMPGROK_LIVE_ENABLE": "1"}, root=tmp_path)
    by_id = {item.id: item for item in gate.evaluate(now=NOW)}
    assert by_id["adapter_registered"].met is False
    assert "no live adapter implementation ships" in by_id["adapter_registered"].reason
