"""Human attribution needs a non-empty actor, not a bare ``human:`` (R22)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pumpgrok.cli.errors import UsageError
from pumpgrok.cli.validators import _human_by
from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.risk.engine.core import RiskEngine
from pumpgrok.risk.killswitch import ClearRefused, KillSwitch
from pumpgrok.risk.strategy_kill import StrategyKillRefused, _human


def test_empty_actor_refused_everywhere() -> None:
    with pytest.raises(UsageError):
        _human_by("human:", "test")
    with pytest.raises(UsageError):
        _human_by("human:   ", "test")
    with pytest.raises(UsageError):
        _human_by("human:bot-00-chief", "test")
    with pytest.raises(StrategyKillRefused):
        _human("human:")
    with pytest.raises(StrategyKillRefused):
        _human("human:bot-04-sniper")
    _human("human:operator")


def test_empty_actor_cannot_clear_the_kill_switch() -> None:
    switch = KillSwitch(clock=FixtureClock())
    approval = SimpleNamespace(
        approved_by="human:", kind="killswitch_clear", id="apr-01JXXXXXXXXXXXXXXXXXXXXXXX"
    )
    with pytest.raises(ClearRefused):
        switch.request_clear(approval, "reason", ts_utc="2026-01-01T00:00:00Z")  # type: ignore[arg-type]


def test_empty_actor_cannot_clear_a_halt() -> None:
    # The halt-clear guard runs before any ledger fold, so an uninitialized
    # engine instance and a bare approval double suffice.
    engine = object.__new__(RiskEngine)
    approval = SimpleNamespace(
        approved_by="human:", kind="halt_clear", id="apr-01JXXXXXXXXXXXXXXXXXXXXXXX"
    )
    with pytest.raises(ValueError, match="must come from a human"):
        engine.request_halt_clear(approval, "reason")  # type: ignore[arg-type]


def test_approval_model_refuses_empty_or_seat_actors() -> None:
    base = {
        "id": "apr-01JXXXXXXXXXXXXXXXXXXXXXXX",
        "kind": "killswitch_clear",
        "raw_message": "clear",
        "at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    for actor in ("human:", "human:bot-00-chief", "risk_engine", "operator"):
        with pytest.raises(ValidationError):
            ApprovalRecord(**base, approved_by=actor)  # type: ignore[arg-type]
    assert ApprovalRecord(**base, approved_by="human:operator").approved_by == "human:operator"

    base_buy = {
        **base,
        "kind": "human_buy",
        "ticket_id": "SOL-20260101-001",
        "mint": "MintAAA",
        "max_slippage_bps": 100,
        "size_lamports": 1_000,
    }
    with pytest.raises(ValidationError):
        ApprovalRecord(**base_buy, approved_by="human:")  # type: ignore[arg-type]
