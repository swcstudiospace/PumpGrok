"""ACCEPTED ledger batches, refusals, and repeat outcomes."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from typing import TYPE_CHECKING

from pumpgrok.core.adapter import Fill, FillStatus, OrderRequest
from pumpgrok.core.errors import OrderRejectedError, OrderUnknownError
from pumpgrok.core.idempotency import exec_place_key
from pumpgrok.execution.paper_adapter.batch_stages import (
    _BatchStagesMixin,
    quote_json_for,
    risk_json_for,
)
from pumpgrok.execution.paper_adapter.models import _rejection_from_row

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore
    from pumpgrok.risk.engine import RiskEngine


class _BatchMixin(_BatchStagesMixin):
    if TYPE_CHECKING:
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
        quote_json = quote_json_for(
            request, quote_id=quote_id, out0=out0, threshold=threshold, impact=impact
        )
        decision = await self._accepted_decision(
            request,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
        )
        risk_json = risk_json_for(decision)
        consume_key, rows = self._consume_rows(
            request,
            decision=decision,
            exit_reason=exit_reason,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
        )
        rows.append(
            self._order_placed_row(
                request,
                order_id=order_id,
                decision=decision,
                quote_json=quote_json,
                risk_json=risk_json,
                ledger_source=ledger_source,
                correlation_id=correlation_id,
            )
        )
        await self._write_order_batch(
            request,
            rows=rows,
            consume_key=consume_key,
            approval_id=decision.approval_id,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
        )

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
