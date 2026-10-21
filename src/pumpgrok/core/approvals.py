"""Human and autonomous approvals (interfaces.md, approvals section; R33).

Persisted in the ledger as `ApprovalRecorded` events, never as JournalNotes.
Consumption (single-send) is a second `ApprovalRecorded` row with `consumed=True`
written inside the same `BEGIN IMMEDIATE` transaction as the `OrderPlaced` it
authorises; `consumed` here is the reduced view of those rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from pumpgrok.core.adapter import OrderRequest


class ApprovalRecord(BaseModel):
    """Parsed human approval phrase `approve <ticket> <mint> <size> <slippage>`
    (size in SOL, converted to lamports once, here), a per-ticket exit-rule
    approval, the RiskEngine's autonomous-paper approval, or a clear/live-gate
    signature. `id` is what exec.place receives as approval_id.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^apr-[0-9A-HJKMNP-TV-Z]{26}$")  # 'apr-' + ULID (R29)
    kind: Literal[
        "human_buy",
        "human_sell",
        "exit_rule",
        "autonomous_paper",
        "killswitch_clear",
        "halt_clear",
        "live_gate",
    ]
    ticket_id: str | None = Field(default=None, pattern=r"^SOL-\d{8}-\d{3}$")
    mint: str | None = None
    size_lamports: int | None = Field(default=None, gt=0)
    token_units: int | None = Field(default=None, gt=0)
    max_slippage_bps: int | None = None
    exit_rule_id: str | None = None
    approved_by: str  # 'human:<name>' for human kinds; 'risk_engine' for autonomous_paper
    raw_message: str
    at: datetime  # Clock time (R27)
    consumed: bool = False  # single-send: one approval, one order

    HUMAN_KINDS: ClassVar[frozenset[str]] = frozenset(
        {
            "human_buy",
            "human_sell",
            "exit_rule",
            "killswitch_clear",
            "halt_clear",
            "live_gate",
        }
    )

    # The order side each kind may authorise. matches() refuses every other side.
    ORDER_SIDES: ClassVar[dict[str, str]] = {
        "human_buy": "buy",
        "human_sell": "sell",
        "exit_rule": "sell",
    }

    @model_validator(mode="after")
    def _human_kinds_need_human(self) -> Self:
        if self.kind in self.HUMAN_KINDS:
            if not self.approved_by.startswith("human:"):
                raise ValueError("human approval must be signed by a human, not a seat")
            if self.kind in ("human_buy", "human_sell") and (
                self.ticket_id is None or self.mint is None or self.max_slippage_bps is None
            ):
                raise ValueError("human trade approval must carry ticket, mint and slippage")
            if self.kind == "human_buy" and self.size_lamports is None:
                raise ValueError("human_buy approval must carry size_lamports")
            if self.kind in ("human_sell", "exit_rule") and self.token_units is None:
                raise ValueError(f"{self.kind} approval must carry token_units")
            if self.kind == "exit_rule" and (self.ticket_id is None or self.exit_rule_id is None):
                raise ValueError("exit_rule approval must name the ticket and the rule (R17)")
        elif self.approved_by != "risk_engine":
            raise ValueError("autonomous_paper approvals are issued by RiskEngine.check only (R24)")
        return self

    def matches(self, request: OrderRequest) -> bool:
        """True only for an unconsumed approval of this order's side that binds this order."""
        if self.consumed or self.ORDER_SIDES.get(self.kind) != request.side.value:
            return False
        if self.ticket_id != request.ticket_id or self.mint != request.mint:
            return False
        if self.max_slippage_bps != request.max_slippage_bps:
            return False
        if request.side.value == "buy":
            return self.size_lamports == request.size_lamports
        return self.token_units == request.token_units
