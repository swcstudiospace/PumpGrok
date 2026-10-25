"""R62 composition wiring: the operator registry loads the reputation book.

``build_operator_registry`` reads ``settings.reputation_path``. A missing file
is an empty healthy book and never refuses. A corrupt file quarantines to a
degraded book, so a buy is refused with ``reputation_degraded`` at the real
composition root.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

import pumpgrok.tools as tools_module
from pumpgrok.config.settings import load_settings
from pumpgrok.core.adapter import OrderRequest
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.tools import build_operator_registry

ROOT = Path(__file__).resolve().parents[2]
START = 1469918176.385
MINT = "So11111111111111111111111111111111111111112"
TICKET = "SOL-20260201-001"


def _buy() -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=MINT,
        side="buy",
        decision_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        size_lamports=200_000_000,
        max_slippage_bps=50,
        approval_id="apr-01ARZ3NDEKTSV4RRFFQ69G5FAW",
        correlation_id="test",
    )


def _build_engine(
    tmp_path: Path, reputation_file: Path, monkeypatch: pytest.MonkeyPatch
) -> RiskEngine:
    """Build the operator registry and return the RiskEngine it constructs."""
    built: list[RiskEngine] = []

    class _RecordingEngine(RiskEngine):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            built.append(self)

    monkeypatch.setattr(tools_module, "RiskEngine", _RecordingEngine)
    settings = load_settings()
    ops = settings.ops.model_copy(update={"reputation_path": str(reputation_file)})
    settings = settings.model_copy(update={"ops": ops})
    _reg, _manifests, client = build_operator_registry(
        data_dir=tmp_path / "desk",
        repo_root=ROOT,
        settings=settings,
        clock=FixtureClock(start=START),
        ledger_path=tmp_path / "ledger.sqlite",
        p_drop=0.0,
    )
    asyncio.run(client.aclose())
    assert len(built) == 1
    return built[0]


def test_corrupt_reputation_file_refuses_buy_at_composition_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reputation_file = tmp_path / "reputation.json"
    reputation_file.write_text("{not json", encoding="utf-8")

    engine = _build_engine(tmp_path, reputation_file, monkeypatch)
    decision = engine.check(_buy(), seat="bot-04-sniper")

    assert decision.passed is False
    assert decision.reason == "reputation_degraded"


def test_missing_reputation_file_does_not_refuse_buy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reputation_file = tmp_path / "absent" / "reputation.json"
    assert not reputation_file.exists()

    engine = _build_engine(tmp_path, reputation_file, monkeypatch)
    decision = engine.check(_buy(), seat="bot-04-sniper")

    assert decision.reason != "reputation_degraded"
