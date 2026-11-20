"""Staged SELL settlement: batch write, CONFIRMING refusals, figures and ledger rows."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from pumpgrok.core.adapter import Fill, FillStatus, OrderRequest
from pumpgrok.core.errors import OrderRejectedError
from pumpgrok.execution.curve_math import sell_out
from pumpgrok.execution.paper_adapter.models import CurveSnapshot
from pumpgrok.replay.clock import parse_ts_utc

if TYPE_CHECKING:
    from pumpgrok.core.ids import Clock, IdFactory
    from pumpgrok.execution.fees import FeeModel
    from pumpgrok.execution.paper_adapter.models import _InflightOrders
    from pumpgrok.ledger.store import LedgerStore


@dataclass(frozen=True)
class SellPlan:
    """Sizing and ACCEPTED quote for one exit, fixed before the batch is written."""

    units: int
    filled_units: int
    fraction: Decimal
    out0: int
    threshold: int
    impact: Decimal
    order_id: str
    quote_id: str


@dataclass(frozen=True)
class SellFigures:
    """Settlement numbers for one exit, fixed once the CONFIRMING checks pass."""

    fraction: Decimal
    gross1: int
    proceeds: int
    network_cost: int
    venue_fee: int
    price_avg: Decimal
    slipped: int
    venue_tx_ref: str


class _SellStagesMixin:
    if TYPE_CHECKING:
        _clock: Clock
        _fees: FeeModel
        _ids: IdFactory
        _inflight: _InflightOrders
        _last_price_ts: dict[str, float]
        _last_reserves: dict[str, tuple[int, int]]
        _store: LedgerStore

        def _fold_state(self) -> Any: ...

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
        ) -> None: ...

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

        def _repeat_outcome(self, request: OrderRequest) -> Fill | OrderRejectedError | None: ...

        async def _await_confirmation(
            self,
            request: OrderRequest,
            *,
            order_id: str,
            forbid_complete: bool,
            ledger_source: str,
            correlation_id: str,
            seat: str | None,
            exit_reason: str | None,
            creator: str | None,
            owner: object,
        ) -> tuple[CurveSnapshot, float, int | None]: ...

    async def _submit_sell(
        self,
        request: OrderRequest,
        plan: SellPlan,
        *,
        ledger_source: str,
        correlation_id: str,
        seat: str | None,
        exit_reason: str | None,
        creator: str | None,
    ) -> Fill | None:
        """Write the ACCEPTED batch; a conflict replays the stored outcome of a repeat."""
        try:
            await self._append_order_batch(
                request,
                order_id=plan.order_id,
                quote_id=plan.quote_id,
                out0=plan.out0,
                threshold=plan.threshold,
                impact=plan.impact,
                ledger_source=ledger_source,
                correlation_id=correlation_id,
                seat=seat,
                exit_reason=exit_reason,
                creator=creator,
            )
        except sqlite3.IntegrityError as exc:
            repeated = self._repeat_outcome(request)
            if isinstance(repeated, Fill):
                return repeated
            if repeated is not None:
                raise repeated from exc
            raise OrderRejectedError(
                "in_flight", "prior attempt recorded no outcome", stage="ACCEPTED"
            ) from exc
        return None

    async def _refuse_sell(
        self,
        request: OrderRequest,
        *,
        order_id: str,
        reason: str,
        detail: str,
        ledger_source: str,
        correlation_id: str,
        quote_out: int = 0,
        threshold: int = 0,
        confirm_out: int = 0,
        fees: int = 0,
    ) -> OrderRejectedError:
        """Discard the in-flight order and record a CONFIRMING refusal."""
        self._inflight.discard(order_id)
        return await self._reject(
            request,
            request.decision_id,
            reason,
            detail,
            stage="CONFIRMING",
            order_id=order_id,
            quote_out=quote_out,
            threshold=threshold,
            confirm_out=confirm_out,
            fees=fees,
            source=ledger_source,
            correlation_id=correlation_id,
        )

    async def _sell_holding_at_confirming(
        self,
        request: OrderRequest,
        plan: SellPlan,
        *,
        ledger_source: str,
        correlation_id: str,
    ) -> Any:
        """The exit must still fit the holding at CONFIRMING; returns the position view."""
        state = self._fold_state()
        pos = state.positions.get(request.mint)
        held = pos.token_units if pos is not None and pos.token_units > 0 else 0
        if plan.filled_units > held:
            # A concurrent exit committed first, or the holding was flattened: this
            # exit no longer fits the holding, so it is refused rather than clipped.
            raise await self._refuse_sell(
                request,
                order_id=plan.order_id,
                reason="no_position",
                detail=(
                    f"mint={request.mint} exit of {plan.filled_units} exceeds holding {held} "
                    "at CONFIRMING"
                ),
                ledger_source=ledger_source,
                correlation_id=correlation_id,
            )
        return pos

    async def _sell_slippage_at_confirming(
        self,
        request: OrderRequest,
        plan: SellPlan,
        *,
        curve1: CurveSnapshot,
        ledger_source: str,
        correlation_id: str,
    ) -> tuple[int, int]:
        """Re-price at the CONFIRMING reserves; returns ``(gross1, out1)`` or refuses."""
        gross1 = sell_out(curve1.s_lamports, curve1.t_units, plan.filled_units)
        out1 = gross1 - self._fees.venue_fee(gross1)
        if out1 < plan.threshold:
            raise await self._refuse_sell(
                request,
                order_id=plan.order_id,
                reason="slippage_exceeded",
                detail=f"confirm {out1} < threshold {plan.threshold}",
                quote_out=plan.out0,
                threshold=plan.threshold,
                confirm_out=out1,
                fees=self._fees.network_cost(),
                ledger_source=ledger_source,
                correlation_id=correlation_id,
            )
        return gross1, out1

    async def _finish_sell(
        self,
        request: OrderRequest,
        plan: SellPlan,
        *,
        curve0: CurveSnapshot,
        ledger_source: str,
        correlation_id: str,
        seat: str | None,
        exit_reason: str | None,
        creator: str | None,
        owner: object,
    ) -> Fill:
        """CONFIRMING: latency, holding and slippage checks, then the settled fill."""
        curve1, latency_s, _ = await self._await_confirmation(
            request,
            order_id=plan.order_id,
            forbid_complete=False,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
            owner=owner,
        )
        pos = await self._sell_holding_at_confirming(
            request, plan, ledger_source=ledger_source, correlation_id=correlation_id
        )
        gross1, out1 = await self._sell_slippage_at_confirming(
            request,
            plan,
            curve1=curve1,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
        )
        figures = self._sell_figures(plan, gross1=gross1, out1=out1)
        return self._settle_sell(
            request,
            plan,
            curve0=curve0,
            curve1=curve1,
            latency_s=latency_s,
            pos=pos,
            figures=figures,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
            exit_reason=exit_reason,
        )

    def _sell_figures(self, plan: SellPlan, *, gross1: int, out1: int) -> SellFigures:
        """Proceeds, fees and slippage for a fill that passed CONFIRMING."""
        network_cost = self._fees.network_cost()
        price_avg = Decimal(gross1) / Decimal(plan.filled_units)
        slipped = (plan.out0 - out1) * 10_000 // plan.out0 if out1 < plan.out0 and plan.out0 else 0
        venue_tx_ref = f"dry_run:{self._ids.ulid()}"
        return SellFigures(
            fraction=plan.fraction,
            gross1=gross1,
            proceeds=out1 - network_cost,
            network_cost=network_cost,
            venue_fee=self._fees.venue_fee(gross1),
            price_avg=price_avg,
            slipped=slipped,
            venue_tx_ref=venue_tx_ref,
        )

    def _sell_fill_row(
        self,
        request: OrderRequest,
        plan: SellPlan,
        *,
        curve0: CurveSnapshot,
        curve1: CurveSnapshot,
        latency_s: float,
        figures: SellFigures,
        ledger_source: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        return {
            "ts_utc": self._now_ts(),
            "source": ledger_source,
            "correlation_id": correlation_id,
            "idempotency_key": f"fill|{plan.order_id}",
            "type": "FillRecorded",
            "payload": {
                "source": ledger_source,
                "order_id": plan.order_id,
                "decision_id": request.decision_id,
                "side": "sell",
                "mint": request.mint,
                "filled_lamports": figures.proceeds,
                "filled_units": plan.filled_units,
                "filled_fraction": str(figures.fraction),
                "price_avg": str(figures.price_avg),
                "venue_fee_lamports": figures.venue_fee,
                "network_cost_lamports": figures.network_cost,
                "cash_delta_lamports": figures.proceeds,
                "latency_s": str(Decimal(str(latency_s))),
                "venue_tx_ref": figures.venue_tx_ref,
                "curve_before_s": curve0.s_lamports,
                "curve_before_t": curve0.t_units,
                "curve_after_s": curve1.s_lamports,
                "curve_after_t": curve1.t_units,
                "route": "curve",
                "realised_slippage_bps": figures.slipped,
            },
        }

    def _position_closed_row(
        self,
        request: OrderRequest,
        plan: SellPlan,
        *,
        pos: Any,
        figures: SellFigures,
        ledger_source: str,
        correlation_id: str,
        exit_reason: str | None,
    ) -> dict[str, Any]:
        realized = figures.proceeds - int(pos.cost_basis_lamports)
        close_reason = exit_reason or "manual"
        pnl_pct = (
            Decimal(realized) / Decimal(int(pos.cost_basis_lamports))
            if int(pos.cost_basis_lamports)
            else Decimal("0")
        )
        try:
            hold_s = int(self._clock.now() - parse_ts_utc(pos.opened_ts_utc))
        except ValueError:
            hold_s = 0
        return {
            "ts_utc": self._now_ts(),
            "source": ledger_source,
            "correlation_id": correlation_id,
            "idempotency_key": f"close|{plan.order_id}",
            "type": "PositionClosed",
            "payload": {
                "source": ledger_source,
                "mint": request.mint,
                "price_exit": str(figures.price_avg),
                "proceeds_lamports": figures.proceeds,
                "realized_pnl_lamports": realized,
                "reason": close_reason,
                "pnl_pct": str(pnl_pct),
                "hold_seconds": max(hold_s, 0),
                "venue_tx_ref": figures.venue_tx_ref,
            },
        }

    def _sell_rows(
        self,
        request: OrderRequest,
        plan: SellPlan,
        *,
        curve0: CurveSnapshot,
        curve1: CurveSnapshot,
        latency_s: float,
        pos: Any,
        figures: SellFigures,
        ledger_source: str,
        correlation_id: str,
        exit_reason: str | None,
    ) -> list[dict[str, Any]]:
        """The FillRecorded row, plus PositionClosed when the exit empties the holding."""
        rows = [
            self._sell_fill_row(
                request,
                plan,
                curve0=curve0,
                curve1=curve1,
                latency_s=latency_s,
                figures=figures,
                ledger_source=ledger_source,
                correlation_id=correlation_id,
            )
        ]
        closes = pos is not None and pos.token_units > 0 and plan.filled_units >= pos.token_units
        if closes and pos is not None:
            rows.append(
                self._position_closed_row(
                    request,
                    plan,
                    pos=pos,
                    figures=figures,
                    ledger_source=ledger_source,
                    correlation_id=correlation_id,
                    exit_reason=exit_reason,
                )
            )
        return rows

    def _settle_sell(
        self,
        request: OrderRequest,
        plan: SellPlan,
        *,
        curve0: CurveSnapshot,
        curve1: CurveSnapshot,
        latency_s: float,
        pos: Any,
        figures: SellFigures,
        ledger_source: str,
        correlation_id: str,
        exit_reason: str | None,
    ) -> Fill:
        """Append the settlement rows atomically and return the filled result."""
        rows = self._sell_rows(
            request,
            plan,
            curve0=curve0,
            curve1=curve1,
            latency_s=latency_s,
            pos=pos,
            figures=figures,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
            exit_reason=exit_reason,
        )
        stored = self._store.append_batch(rows)
        self._inflight.discard(plan.order_id)
        self._last_price_ts[request.mint] = self._clock.now()
        self._last_reserves[request.mint] = (curve1.s_lamports, curve1.t_units)
        return Fill(
            order_id=plan.order_id,
            decision_id=request.decision_id,
            status=FillStatus.FILLED if plan.filled_units == plan.units else FillStatus.PARTIAL,
            venue_tx_ref=figures.venue_tx_ref,
            filled_lamports=figures.proceeds,
            filled_units=plan.filled_units,
            filled_fraction=figures.fraction,
            price_avg=figures.price_avg,
            realised_slippage_bps=figures.slipped,
            venue_fee_lamports=figures.venue_fee,
            network_cost_lamports=figures.network_cost,
            route="curve",
            ledger_seq=int(stored[0]["seq"]),
        )
