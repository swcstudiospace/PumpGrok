"""Staged ACCEPTED batch: risk re-check, approval consumption and the OrderPlaced row."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.errors import OrderRejectedError
from pumpgrok.core.idempotency import canonical_json, exec_place_key
from pumpgrok.execution.paper_adapter.models import _at_iso
from pumpgrok.risk.engine import RULE_EXIT_REASONS

if TYPE_CHECKING:
    from decimal import Decimal

    from pumpgrok.ledger.store import LedgerStore
    from pumpgrok.risk.engine import RiskDecision, RiskEngine


def quote_json_for(
    request: OrderRequest,
    *,
    quote_id: str,
    out0: int,
    threshold: int,
    impact: Decimal,
) -> str:
    """Canonical quote snapshot stored on OrderPlaced (informational; source=curve)."""
    return canonical_json(
        {
            "in_amount": int(request.size_lamports or 0),
            "out_amount": out0,
            "other_amount_threshold": threshold,
            "price_impact_pct": impact,
            "source": "curve",
            "quote_id": quote_id,
            "jupiter_quote_id": request.quote_id,
        }
    )


def risk_json_for(decision: RiskDecision) -> str:
    """Canonical risk snapshot stored on OrderPlaced, bound to the decision."""
    return canonical_json(
        {
            "reason": decision.reason,
            "order_hash": decision.order_hash,
            "capped": decision.capped,
            "caps": decision.caps,
        }
    )


class _BatchStagesMixin:
    if TYPE_CHECKING:
        _risk: RiskEngine
        _store: LedgerStore

        def _now_ts(self) -> str: ...

        async def _reject(
            self,
            request: OrderRequest,
            decision_id: str,
            reason: str,
            detail: str,
            *,
            stage: str,
            order_id: str | None = None,
            quote_out: int = 0,
            threshold: int = 0,
            confirm_out: int = 0,
            fees: int = 0,
            source: str,
            correlation_id: str,
        ) -> OrderRejectedError: ...

    async def _accepted_decision(
        self,
        request: OrderRequest,
        *,
        seat: str | None,
        exit_reason: str | None,
        creator: str | None,
        ledger_source: str,
        correlation_id: str,
    ) -> RiskDecision:
        """ACCEPTED risk re-check; a refusal is recorded and raised, no order is written."""
        decision = self._risk.check(
            request,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
            source=ledger_source,
            correlation_id=correlation_id,
            stage="ACCEPTED",
        )
        if not decision.passed:
            raise await self._reject(
                request,
                request.decision_id,
                decision.reason,
                "ACCEPTED re-check refused; no order written",
                stage="ACCEPTED",
                source=ledger_source,
                correlation_id=correlation_id,
            )
        return decision

    def _consume_rows(
        self,
        request: OrderRequest,
        *,
        decision: RiskDecision,
        exit_reason: str | None,
        ledger_source: str,
        correlation_id: str,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """The approval consumption row, when this decision consumes an approval."""
        approval = decision.approval
        if (
            approval is None
            or decision.approval_id is None
            or (approval.approved_by == "risk_engine" and exit_reason not in RULE_EXIT_REASONS)
        ):
            return None, []
        consume_key = f"consume|{decision.approval_id}"
        row: dict[str, Any] = {
            "ts_utc": self._now_ts(),
            "source": ledger_source,
            "correlation_id": correlation_id,
            "idempotency_key": consume_key,
            "type": "ApprovalRecorded",
            "payload": {
                "source": ledger_source,
                "id": approval.id,
                "kind": approval.kind,
                "approved_by": approval.approved_by,
                "at": _at_iso(approval.at),
                "ticket_id": approval.ticket_id or "",
                "mint": approval.mint or "",
                "size_lamports": approval.size_lamports or 0,
                "token_units": approval.token_units or 0,
                "max_slippage_bps": approval.max_slippage_bps or 0,
                "exit_rule_id": approval.exit_rule_id or "",
                "raw_message": approval.raw_message,
                "consumed": True,
            },
        }
        return consume_key, [row]

    def _order_placed_row(
        self,
        request: OrderRequest,
        *,
        order_id: str,
        decision: RiskDecision,
        quote_json: str,
        risk_json: str,
        ledger_source: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        approval = decision.approval
        size = int(request.size_lamports or 0)
        return {
            "ts_utc": self._now_ts(),
            "source": ledger_source,
            "correlation_id": correlation_id,
            "idempotency_key": exec_place_key(
                request.ticket_id, request.side.value, request.decision_id
            ),
            "type": "OrderPlaced",
            "payload": {
                "source": ledger_source,
                "order_id": order_id,
                "decision_id": request.decision_id,
                "ticket_id": request.ticket_id,
                "side": request.side.value,
                "mint": request.mint,
                "slippage_bps": int(request.max_slippage_bps),
                "size_lamports": size if request.side is Side.BUY else 0,
                "token_units": int(request.token_units or 0) if request.side is Side.SELL else 0,
                "quote_json": quote_json,
                "approval_json": canonical_json(
                    {
                        "approval_id": decision.approval_id or "",
                        "kind": approval.kind if approval is not None else "",
                    }
                ),
                "risk_json": risk_json,
            },
        }

    async def _write_order_batch(
        self,
        request: OrderRequest,
        *,
        rows: list[dict[str, Any]],
        consume_key: str | None,
        approval_id: str | None,
        ledger_source: str,
        correlation_id: str,
    ) -> None:
        """Append the batch atomically; a lost approval race refuses as approval_missing."""
        try:
            self._store.append_batch(rows)
        except sqlite3.IntegrityError as exc:
            # The consume row is keyed per approval: a concurrent order that
            # consumed it first rolls this whole batch back. The stored consume
            # row tells that apart from a repeated decision (handled by callers).
            placed = exec_place_key(request.ticket_id, request.side.value, request.decision_id)
            if (
                consume_key is not None
                and self._store.by_key(consume_key) is not None
                and self._store.by_key(placed) is None
            ):
                raise await self._reject(
                    request,
                    request.decision_id,
                    "approval_missing",
                    f"approval {approval_id} consumed by a concurrent order",
                    stage="ACCEPTED",
                    source=ledger_source,
                    correlation_id=correlation_id,
                ) from exc
            raise
