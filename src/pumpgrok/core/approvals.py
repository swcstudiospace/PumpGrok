"""Human and autonomous approvals (interfaces.md, approvals section; R33).

Persisted in the ledger as `ApprovalRecorded` events, never as JournalNotes.
Consumption (single-send) is a second `ApprovalRecorded` row with `consumed=True`
written inside the same `BEGIN IMMEDIATE` transaction as the `OrderPlaced` it
authorises; `consumed` here is the reduced view of those rows.

A human trade approval is the exact phrase
`approve <ticket> <mint> <size-sol> <slippage-bps>` (constitution 2, R17):
five whitespace-separated tokens, matched token for token against the ticket.
`size-sol` is decimal SOL at the phrase boundary, converted once to lamports
here (R28). The phrase carries no side: the caller names `human_buy` (buys)
or `human_sell` (sells sized in SOL notional, with units derived at the
decision curve inside the adapter, or directly in token units). `exit_rule`
approvals always carry `token_units` from the rule engine and never come from a phrase.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pumpgrok.core.units import sol_to_lamports

if TYPE_CHECKING:
    from pumpgrok.core.adapter import OrderRequest
    from pumpgrok.ledger.store import LedgerStore

TICKET_RE = re.compile(r"^SOL-\d{8}-\d{3}$")


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
            if self.kind == "human_sell" and (
                self.size_lamports is None and self.token_units is None
            ):
                raise ValueError("human_sell approval must carry size_lamports or token_units")
            if self.kind == "exit_rule" and self.token_units is None:
                raise ValueError("exit_rule approval must carry token_units")
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
        return self._size_matches(request)

    def _size_matches(self, request: OrderRequest) -> bool:
        """Every size leg the approval states must agree with the request.

        A SOL-notional approval binds SOL-sized requests only. The adapter
        prefers ``token_units`` over ``size_lamports``, so a request that also
        carries units would sell a different amount than the one approved; it is
        refused rather than trusted. A unit-stated approval must match on units.
        """
        if request.side.value == "buy" or self.kind == "human_sell":
            size_ok = self.size_lamports is None or self.size_lamports == request.size_lamports
            if self.token_units is not None:
                units_ok = self.token_units == request.token_units
            else:
                units_ok = request.token_units is None
            return size_ok and units_ok
        if self.kind == "exit_rule":
            return self.token_units == request.token_units
        if self.kind == "autonomous_paper":
            if request.token_units is not None and self.token_units is not None:
                return self.token_units == request.token_units
            return self.size_lamports == request.size_lamports
        return False


_BASE58 = frozenset("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")


def _sol_to_lamports(size_sol: str) -> int:
    """Decimal SOL to integer lamports, once, at the phrase boundary (R28)."""
    try:
        size = Decimal(size_sol)
    except InvalidOperation as exc:
        raise ValueError(f"bad size {size_sol!r}: want decimal SOL") from exc
    if not size.is_finite():
        raise ValueError(f"bad size {size_sol!r}: want a finite number")
    if size <= 0:
        raise ValueError(f"bad size {size_sol!r}: want a positive number")
    return sol_to_lamports(size)


def parse_human_phrase(
    phrase: str,
    *,
    kind: Literal["human_buy", "human_sell"],
    by: str,
    approval_id: str,
    at: datetime,
) -> ApprovalRecord:
    """Parse `approve <ticket> <mint> <size-sol> <slippage-bps>` token for token.

    Exactly five whitespace-separated tokens; any deviation raises ValueError
    (the caller maps it to `approval_mismatch`: never treat a near-match as
    approval). The phrase carries no side: `kind` names which side it
    authorises. `by` must be `human:<name>`, never a seat id.
    """
    parts = phrase.split()
    if len(parts) != 5 or parts[0] != "approve":
        raise ValueError(
            "bad approval phrase: want five whitespace-separated tokens "
            "`approve <ticket> <mint> <size> <slippage>`"
        )
    _, ticket_id, mint, size_sol, slippage_raw = parts
    if not TICKET_RE.fullmatch(ticket_id):
        raise ValueError(f"bad approval phrase ticket {ticket_id!r}: want SOL-YYYYMMDD-NNN")
    if not 32 <= len(mint) <= 44 or any(char not in _BASE58 for char in mint):
        raise ValueError("bad approval phrase mint: want 32-44 base58 characters")
    try:
        slippage_bps = int(slippage_raw)
    except ValueError as exc:
        raise ValueError(f"bad approval phrase slippage {slippage_raw!r}: want int bps") from exc
    if not 0 <= slippage_bps <= 10_000:
        raise ValueError(f"bad approval phrase slippage {slippage_raw!r}: want 0-10000 bps")
    return ApprovalRecord(
        id=approval_id,
        kind=kind,
        ticket_id=ticket_id,
        mint=mint,
        size_lamports=_sol_to_lamports(size_sol),
        max_slippage_bps=slippage_bps,
        approved_by=by,
        raw_message=phrase,
        at=at,
    )


def record_human_approval(
    store: LedgerStore,
    record: ApprovalRecord,
    *,
    ts_utc: str,
    source: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Append one unconsumed `ApprovalRecorded` row for a parsed human phrase."""
    return store.append(
        ts_utc=ts_utc,
        source=source,
        correlation_id=correlation_id,
        idempotency_key=f"approval|{record.id}",
        type="ApprovalRecorded",
        payload={
            "source": source,
            "id": record.id,
            "kind": record.kind,
            "approved_by": record.approved_by,
            "at": record.at.isoformat(),
            "ticket_id": record.ticket_id or "",
            "mint": record.mint or "",
            "size_lamports": record.size_lamports or 0,
            "token_units": record.token_units or 0,
            "max_slippage_bps": record.max_slippage_bps or 0,
            "exit_rule_id": record.exit_rule_id or "",
            "raw_message": record.raw_message,
            "consumed": False,
        },
    )
