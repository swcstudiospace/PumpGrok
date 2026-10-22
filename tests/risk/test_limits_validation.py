"""Daily-loss halt threshold is a floor (INV-C-06).

Configuration may lower ``daily_loss_halt_fraction`` but never raise it
above 5 %: the bound is the INV-S-09 constitution constant, inlined here
as ``Decimal("0.05")`` in ``RiskBudget`` with a validator that rejects
anything higher.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pumpgrok.config.settings import ConfigError, load_settings
from pumpgrok.core.risk_budget import RiskBudget


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def test_daily_loss_halt_cannot_exceed_constitution() -> None:
    """INV-C-06: 0.051 raises; 0.05 and below load."""
    with pytest.raises(ValidationError):
        RiskBudget(daily_loss_halt_fraction=Decimal("0.051"))
    assert RiskBudget(daily_loss_halt_fraction=Decimal("0.05")).daily_loss_halt_fraction == Decimal(
        "0.05"
    )
    assert RiskBudget(daily_loss_halt_fraction=Decimal("0.01")).daily_loss_halt_fraction == Decimal(
        "0.01"
    )


def test_daily_loss_halt_env_capped_at_startup(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INV-C-06: the loader surfaces the cap as a startup failure."""
    monkeypatch.setenv("PUMPGROK_RISK__DAILY_LOSS_HALT_FRACTION", "0.051")
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert "daily_loss_halt_fraction" in str(excinfo.value)
