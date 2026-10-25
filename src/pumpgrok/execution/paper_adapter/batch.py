"""ACCEPTED ledger batches, refusals, and repeat outcomes."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from pumpgrok.core.adapter import Fill, FillStatus, OrderRequest, Side
from pumpgrok.core.errors import OrderRejectedError, OrderUnknownError
from pumpgrok.core.idempotency import canonical_json, exec_place_key
from pumpgrok.execution.paper_adapter.models import _at_iso, _rejection_from_row
from pumpgrok.risk.engine import RULE_EXIT_REASONS


class _BatchMixin:
    if TYPE_CHECKING:
        from pumpgrok.ledger.store import LedgerStore
        from pumpgrok.risk.engine import RiskEngine

        _risk: RiskEngine
        _store: LedgerStore

        def _now_ts(self) -> str: ...

    async def _append_order_batch(
        self,
        request: OrderRequest,
        *,
        order_id: str,
        quote_id: str,
        out0: int,
        threshold: int,
        impact: Decimal,
        ledger_source: str,
        correlation_id: str,
        seat: str | None = None,
        exit_reason: str | None = None,
        creator: str | None = None,
    ) -> None:
        quote_json = canonical_json(
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
        risk_json = canonical_json(
            {
                "reason": decision.reason,
                "order_hash": decision.order_hash,
                "capped": decision.capped,
                "caps": decision.caps,
            }
        )
        size = int(request.size_lamports or 0)
        rows: list[dict[str, Any]] = []
        consume_key: str | None = None
        approval = decision.approval
        if (
            approval is not None
            and (approval.approved_by != "risk_engine" or exit_reason in RULE_EXIT_REASONS)
            and decision.approval_id is not None
        ):
            consume_key = f"consume|{decision.approval_id}"
            rows.append(
                {
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
            )
        rows.append(
            {
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
                    "token_units": int(request.token_units or 0)
                    if request.side is Side.SELL
                    else 0,
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
        )
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
                    f"approval {decision.approval_id} consumed by a concurrent order",
                    stage="ACCEPTED",
                    source=ledger_source,
                    correlation_id=correlation_id,
                ) from exc
            raise

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
    ) -> OrderRejectedError:
        err: OrderRejectedError = OrderRejectedError(
            reason, detail, stage=stage, fees_lamports=fees
        )
        key = f"reject|{request.ticket_id}|{request.side.value}|{decision_id}|{stage}|{reason}"
        try:
            self._store.append(
                ts_utc=self._now_ts(),
                source=source,
                correlation_id=correlation_id,
                idempotency_key=key,
                type="OrderRejected",
                payload={
                    "source": source,
                    "order_id": order_id or f"unplaced-{decision_id}",
                    "decision_id": decision_id,
                    "reason": reason,
                    "detail": f"{detail} ticket={request.ticket_id} mint={request.mint}",
                    "stage": stage,
                    "fees_lamports": fees,
                    "quote_out": quote_out,
                    "other_amount_threshold": threshold,
                    "confirm_out": confirm_out,
                },
            )
        except sqlite3.IntegrityError:
            # A repeated decision replays the first refusal (R23): the same
            # (ticket, side, decision, stage, reason) key is already stored,
            # so return the stored outcome instead of leaking a traceback.
            stored = self._store.by_key(key)
            if stored is None:
                raise
            return _rejection_from_row(stored, fallback=err)
        return err

    def _repeat_outcome(self, request: OrderRequest) -> Fill | OrderRejectedError | None:
        """First outcome for a repeated decision, or None on first attempt."""
        key = exec_place_key(request.ticket_id, request.side.value, request.decision_id)
        placed = self._store.by_key(key)
        if placed is None:
            return None
        payload = placed.get("payload", {})
        if not isinstance(payload, dict):
            return None
        order_id = str(payload.get("order_id", ""))
        for event in self._store.read(limit=None):
            if event.get("type") not in ("FillRecorded", "OrderRejected"):
                continue
            body = event.get("payload", {})
            if not isinstance(body, dict) or str(body.get("order_id", "")) != order_id:
                continue
            if event["type"] == "FillRecorded":
                return Fill(
                    order_id=order_id,
                    decision_id=str(body.get("decision_id", "")),
                    status=(
                        FillStatus.FILLED
                        if Decimal(str(body.get("filled_fraction", "1"))) >= 1
                        else FillStatus.PARTIAL
                    ),
                    venue_tx_ref=str(body.get("venue_tx_ref", "")),
                    filled_lamports=int(body.get("filled_lamports", 0)),
                    filled_units=int(body.get("filled_units", 0)),
                    filled_fraction=Decimal(str(body.get("filled_fraction", "1"))),
                    price_avg=Decimal(str(body.get("price_avg", "0"))),
                    realised_slippage_bps=int(body.get("realised_slippage_bps", 0)),
                    venue_fee_lamports=int(body.get("venue_fee_lamports", 0)),
                    network_cost_lamports=int(body.get("network_cost_lamports", 0)),
                    route=str(body.get("route", "curve")),
                    ledger_seq=int(event.get("seq", 0)),
                )
            reason = str(body.get("reason", ""))
            if reason == "confirmation_timeout":
                return OrderUnknownError(
                    reason,
                    str(body.get("detail", "")),
                    stage=str(body.get("stage", "ACCEPTED")),
                    fees_lamports=int(body.get("fees_lamports", 0)),
                )
            return OrderRejectedError(
                reason,
                str(body.get("detail", "")),
                stage=str(body.get("stage", "ACCEPTED")),
                fees_lamports=int(body.get("fees_lamports", 0)),
            )
        return OrderRejectedError(
            "in_flight", "prior attempt recorded no outcome", stage="ACCEPTED"
        )
