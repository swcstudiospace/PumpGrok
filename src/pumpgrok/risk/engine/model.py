"""Bound decisions, walk state and shared helpers for the risk engine."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.ledger.reducer import LedgerState
from pumpgrok.ledger.store import LedgerInconsistent
from pumpgrok.replay.clock import format_ts_utc


class RiskDecision(BaseModel):
    """One bound decision. ``reason`` is the first-failure R34 id, or ``pass``.

    A degraded reputation book (R62) refuses buys with the breaker-scope
    reason ``reputation_degraded``; the ``breaker_open`` evaluated row reads
    ``fail`` so the 19 R34 rows never change shape.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    reason: str
    order_hash: str
    decision_id: str
    approval_id: str | None = None
    approval: ApprovalRecord | None = None
    size_lamports: int | None = None
    token_units: int | None = None
    capped: bool = False
    caps: dict[str, int] = Field(default_factory=dict)
    probe: bool = False
    evaluated: list[dict[str, str]] = Field(default_factory=list)


def order_hash_for(order: OrderRequest) -> str:
    """Bind a decision to its order: sha256 over the canonical order fields."""
    return hashlib.sha256(
        canonical_json(
            {
                "ticket_id": order.ticket_id,
                "side": order.side.value,
                "decision_id": order.decision_id,
                "mint": order.mint,
                "size_lamports": order.size_lamports,
                "token_units": order.token_units,
                "max_slippage_bps": order.max_slippage_bps,
            }
        ).encode("utf-8")
    ).hexdigest()


def halt_key(reason: str, day_utc: str) -> str:
    """Idempotency per (reason, utc_day): one ``HaltSet`` per reason per day."""
    return hashlib.sha256(f"HaltSet|{reason}|{day_utc}".encode()).hexdigest()


def utc_day(now_s: float) -> str:
    """UTC calendar day of an epoch timestamp."""
    return format_ts_utc(now_s)[:10]


class _Fail(Exception):
    """Internal: abort the step walk with the failing step id and detail."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


@dataclass
class _StepCtx:
    """Mutable walk state shared by the 19 step methods."""

    order: OrderRequest
    seat: str | None
    exit_reason: str | None
    creator: str | None
    source: str
    correlation_id: str
    stage: str
    is_buy: bool
    is_exit_sell: bool
    wanted: set[str]
    state: LedgerState
    kill: tuple[str, str, bool] | None
    open_breakers: set[str]
    killed: set[str]
    equity: int
    approvals: dict[str, ApprovalRecord]
    half_blocked: bool = False
    evaluated: dict[str, str] = field(default_factory=dict)
    approval: ApprovalRecord | None = None
    approval_id: str | None = None
    final_size: int | None = None
    caps: dict[str, int] = field(default_factory=dict)
    capped: bool = False
    probe: bool = False

    def mark(self, step: str, status: str = "pass") -> None:
        """Record a step outcome (call args keep password-wording lints quiet)."""
        self.evaluated[step] = status


class _suppress_integrity:
    """Idempotent halt rows: already-set or unwritable is not an error.

    A duplicate key means another path already recorded the breach. A
    latched handle (``LedgerInconsistent``) cannot record anything; the
    verify failure itself is the persistent signal, so the append is dropped.
    """

    def __enter__(self) -> _suppress_integrity:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return isinstance(exc, (sqlite3.IntegrityError, LedgerInconsistent))

