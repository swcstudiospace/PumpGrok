"""Per-seat ceilings and the desk-level risk budget (interfaces.md 2.9, R20).

The ONLY risk-budget schema. The config loader (``[risk]`` overlay keys) and the
bot manifests (``risk_budget``) both validate against this class, so one limit
cannot pass one check and fail the other.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RiskBudget(BaseModel):
    """Per-seat ceilings and the desk-level budget. The ONLY risk-budget schema (R20).

    Fractions are of equity in 0..1 (never percent). Money is `int`; prices are
    `Decimal`. `paper_equity_sol` is the one SOL-denominated config value; it is
    converted to lamports once at load (R28).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_trade_fraction: Decimal = Field(default=Decimal("0.02"), ge=0, le=1)
    max_token_fraction: Decimal = Field(default=Decimal("0.05"), ge=0, le=1)
    daily_loss_halt_fraction: Decimal = Field(default=Decimal("0.05"), ge=0, le=1)
    drawdown_halt_fraction: Decimal = Field(default=Decimal("0.15"), ge=0, le=1)
    max_open_positions: int = Field(default=3, ge=0)
    max_trades_per_day: int = Field(default=20, ge=0)
    liquidity_floor_multiple: int = Field(default=10, ge=1)
    partial_fill_fraction: Decimal = Field(default=Decimal("0.02"), gt=0, le=1)
    paper_equity_sol: Decimal = Field(default=Decimal("10"), gt=0)

    @field_validator("daily_loss_halt_fraction")
    @classmethod
    def _cap_daily_loss(cls, v: Decimal) -> Decimal:
        if v > Decimal("0.05"):
            raise ValueError(f"daily_loss_halt_fraction {v} exceeds the 0.05 cap (INV-C-06)")
        return v

    @property
    def paper_equity_lamports(self) -> int:
        return budget_equity_lamports(self)

    @property
    def may_open_exposure(self) -> bool:
        return self.max_trade_fraction > 0 and self.max_open_positions > 0


LAMPORTS_PER_SOL = 1_000_000_000


def budget_equity_lamports(budget: RiskBudget) -> int:
    """Configured paper equity in lamports, rounded half up (the one SOL-to-lamports rule).

    Every equity source (scheduler, engine, tools, the budget property) goes through here,
    so one configured value yields one lamport amount on every path.
    """
    scaled = budget.paper_equity_sol * LAMPORTS_PER_SOL
    return int(scaled.to_integral_value(rounding=ROUND_HALF_UP))
