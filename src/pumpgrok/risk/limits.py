"""Engine knobs that are not part of the risk budget (paper-engine.md 5.2).

``RiskBudget`` (``core/risk_budget.py``) is the ONLY risk-budget schema (R20):
nine fraction keys plus ``paper_equity_sol``, read from the TOML ``[risk]``
block. Everything here is an engine knob that is not part of that budget.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EngineLimits(BaseModel):
    """``[limits]`` knobs: floors, gates and bases (all REVIEW defaults).

    ``mtm_interval_s`` mirrors the journal seat mark cadence (design 2.7):
    equity used for the fraction and halt steps must come from a
    ``MarkToMarket`` younger than this, else the order is ``data_stale``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    min_trade_lamports: int = Field(default=10_000_000, ge=1)
    max_slippage_bps: int = Field(default=300, ge=0, le=10_000)
    one_position_per_creator: bool = True
    daily_loss_basis: Literal["total", "realized"] = "total"
    blind_max_s: float = Field(default=300.0, ge=0)
    mtm_interval_s: float = Field(default=60.0, gt=0)
