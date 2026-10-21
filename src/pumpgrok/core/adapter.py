"""Execution contracts: orders, quotes, fills, positions, and adapters (interfaces.md 2.7).

Money is integer base units (R28): a BUY names `size_lamports`, a SELL names
`token_units`. Prices are Decimal lamports per token base unit.
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar, Literal, Protocol, Self, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pumpgrok.core.ids import ULID_RE


class Side(enum.StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderRequest(BaseModel):
    """Input of exec.place / exec.simulate. The idempotency key is NOT a caller field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str = Field(pattern=r"^SOL-\d{8}-\d{3}$")
    mint: str = Field(min_length=32, max_length=44)
    side: Side
    decision_id: str = Field(pattern=ULID_RE)
    size_lamports: int | None = Field(default=None, gt=0)
    token_units: int | None = Field(default=None, gt=0)
    max_slippage_bps: int = Field(ge=1, le=10_000)
    approval_id: str = Field(pattern=r"^apr-[0-9A-HJKMNP-TV-Z]{26}$")
    quote_id: str | None = None
    correlation_id: str

    @model_validator(mode="after")
    def _size_matches_side(self) -> Self:
        if self.side is Side.BUY and self.size_lamports is None:
            raise ValueError("buy requires size_lamports")
        if self.side is Side.SELL and self.token_units is None:
            raise ValueError("sell requires token_units")
        return self

    @property
    def idempotency_scope(self) -> str:
        return f"{self.ticket_id}:{self.side}:{self.decision_id}"


class Quote(BaseModel):
    """`source="curve"` quotes are the fill basis; `source="jupiter"` quotes are
    informational (route, priority) and never the fill price (R38)."""

    model_config = ConfigDict(frozen=True)

    quote_id: str
    in_amount: int  # lamports (BUY) or token base units (SELL)
    out_amount: int  # token base units (BUY) or lamports (SELL)
    other_amount_threshold: int  # same unit as out_amount
    price_impact_pct: Decimal
    route_plan: list[dict[str, Any]]
    context_slot: int | None
    source: Literal["jupiter", "curve"]
    expires_at: datetime


class SimulationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    would_fill: bool
    fill_kind: Literal["full", "partial", "rejected"]
    price_expected: Decimal  # lamports per token base unit
    expected_out: int  # token base units (BUY) or lamports (SELL)
    price_impact_pct: Decimal
    venue_fee_lamports: int
    network_cost_lamports: int  # base fee + priority fee
    liquidity_ratio: Decimal  # S0 / size_lamports
    rejection_reason: str | None
    latency_ms_estimate: int


class FillStatus(enum.StrEnum):
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class Fill(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str = Field(pattern=ULID_RE)
    decision_id: str = Field(pattern=ULID_RE)
    status: FillStatus
    venue_tx_ref: str = Field(pattern=r"^dry_run:[0-9A-HJKMNP-TV-Z]{26}$")  # never a real signature
    filled_lamports: int
    filled_units: int  # token base units
    filled_fraction: Decimal
    price_avg: Decimal  # lamports per token base unit
    realised_slippage_bps: int
    venue_fee_lamports: int
    network_cost_lamports: int
    route: str
    ledger_seq: int
    reason: str | None = None


class Position(BaseModel):
    """Integer base units plus marks. `mtm_frozen` is set by the `graduated` and
    `blind_flatten` paths (R8, R25)."""

    model_config = ConfigDict(frozen=True)

    ticket_id: str
    mint: str
    correlation_id: str
    price_entry: Decimal  # lamports per token base unit
    price_peak: Decimal
    cost_basis_lamports: int  # cash debited incl. all fees
    token_units: int
    opened_at: datetime
    price_mark: Decimal | None = None
    last_mtm_lamports: int | None = None
    unrealised_pnl_lamports: int | None = None
    unrealised_pnl_pct: Decimal | None = None
    mtm_source: Literal["live", "last_good"] = "live"
    mtm_frozen: bool = False
    hold_seconds: int = 0


class ExecutionMode(enum.StrEnum):
    PAPER = "paper"
    LIVE = "live"


@runtime_checkable
class ExecutionAdapter(Protocol):
    """Common interface for PaperAdapter (enabled) and the live stub (disabled)."""

    mode: ClassVar[ExecutionMode]
    venue: ClassVar[str]  # 'paper' | 'disabled'

    async def quote(
        self, input_mint: str, output_mint: str, amount: int, slippage_bps: int
    ) -> Quote: ...

    async def simulate(self, request: OrderRequest) -> SimulationResult: ...

    async def place(self, request: OrderRequest) -> Fill: ...

    async def cancel(self, order_id: str, ticket_id: str, decision_id: str) -> bool: ...

    # True only while the order is ACCEPTED; False once the latency sleep has completed.

    async def positions(self, mint: str | None = None) -> Sequence[Position]: ...
