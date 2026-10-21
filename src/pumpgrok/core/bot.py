"""Bot manifests and the per-seat risk budget (interfaces.md 2.9, R20)."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    Protocol,
    Self,
    runtime_checkable,
)

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pumpgrok.core.side_effect import MAX_GRANTABLE_SIDE_EFFECT, SideEffect

if TYPE_CHECKING:
    from pumpgrok.core.registry import ToolRegistry


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
        return int(self.paper_equity_sol * 1_000_000_000)

    @property
    def may_open_exposure(self) -> bool:
        return self.max_trade_fraction > 0 and self.max_open_positions > 0


class Schedule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["cron", "interval", "event"]
    expr: str  # cron expression, 'every 15m', or event kind


class ToolGrant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str  # catalog name, e.g. 'exec.place'
    side_effect: SideEffect  # the class the seat is granted for this tool

    @field_validator("side_effect")
    @classmethod
    def _never_live(cls, v: SideEffect) -> SideEffect:
        if v.exceeds(MAX_GRANTABLE_SIDE_EFFECT):
            raise ValueError("live-write can never be granted")
        return v


class BotManifest(BaseModel):
    """One per seat. `risk_budget` carries the nine R20 keys; money is int."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^bot-0[0-9]-[a-z-]+$")  # SEAT_RE (R19)
    display: str
    channel: Literal["Trading Floor", "DM"]
    purpose: str
    inputs: list[str]
    outputs: list[str]
    skills: list[str]
    allowed_tools: list[ToolGrant]
    risk_budget: RiskBudget
    forbidden: list[str]
    fail_safe: str
    schedule: list[Schedule]
    escalation: list[str]
    owned_paths: list[str]
    receipts_dir: str
    prompt_source: str
    writes_to_exchange: bool = False

    def grant_for(self, tool_name: str) -> ToolGrant | None:
        for g in self.allowed_tools:
            if g.name == tool_name:
                return g
        return None

    @model_validator(mode="after")
    def _exec_writes_only_for_writers(self) -> Self:
        paper_writers = {"bot-04-sniper", "bot-06-exit"}
        for g in self.allowed_tools:
            if g.name.startswith("exec.") and g.side_effect is SideEffect.PAPER_WRITE:
                if self.id not in paper_writers:
                    raise ValueError(f"{self.id} may not hold paper-write exec tools")
                if not self.writes_to_exchange:
                    raise ValueError(f"{self.id} holds exec writes but writes_to_exchange is false")
            if g.name == "risk.kill_switch" and self.id != "bot-02-risk":
                raise ValueError(f"{self.id} may not hold risk.kill_switch")
            if g.name == "notify.alert" and self.id in ("bot-02-risk", "bot-05-rug"):
                raise ValueError(
                    f"{self.id} escalates via desk.event_emit kind=escalation; "
                    "the supervisor relays to notify.alert (R35)"
                )
            if g.name == "portfolio.ledger_write":
                raise ValueError("portfolio.ledger_write is adapter-only, never a seat grant")
        return self


@runtime_checkable
class Bot(Protocol):
    manifest: ClassVar[BotManifest]

    async def cycle(
        self, registry: ToolRegistry, trigger: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    async def heartbeat(self) -> Any: ...
