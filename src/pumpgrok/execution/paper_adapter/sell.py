"""SELL target sizing and settlement."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from pumpgrok.core.adapter import Fill, FillStatus, OrderRequest
from pumpgrok.core.errors import OrderRejectedError
from pumpgrok.execution.curve_math import impact_sell, sell_out
from pumpgrok.execution.paper_adapter.models import CurveSnapshot
from pumpgrok.replay.clock import parse_ts_utc


class _SellMixin:
    if TYPE_CHECKING:
        from pumpgrok.core.ids import Clock, IdFactory
        from pumpgrok.execution.fees import FeeModel
        from pumpgrok.execution.paper_adapter.models import _InflightOrders
        from pumpgrok.ledger.store import LedgerStore

        _clock: Clock
        _fees: FeeModel
        _ids: IdFactory
        _inflight: _InflightOrders
        _last_price_ts: dict[str, float]
        _last_reserves: dict[str, tuple[int, int]]
        _store: LedgerStore

        def _fold_state(self) -> Any: ...

        def _now_ts(self) -> str: ...

        def _fill_cap(self, s_lamports: int) -> int: ...

        def _floor(self, size_lamports: int) -> int: ...

        def _open_units(self, mint: str) -> int: ...

        def _slippage_bps(self, request: OrderRequest) -> int: ...

        @staticmethod
        def _sell_units(request: OrderRequest, curve: CurveSnapshot) -> int: ...

        async def _read_curve(self, mint: str) -> CurveSnapshot | None: ...

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

        def _repeat_outcome(
            self, request: OrderRequest
        ) -> Fill | OrderRejectedError | None: ...

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

    async def _sell_targets(
        self,
        request: OrderRequest,
        curve0: CurveSnapshot,
        *,
        ledger_source: str,
        correlation_id: str,
    ) -> tuple[int, int]:
        """Validated ``(units, filled_units)`` for a sell at the decision curve.

        Refuses with ``no_position`` when flat and caps the fill at the open
        position; the requested units stay uncapped so an over-size exit
        reports ``partial`` instead of a quiet ``filled``.
        """
        units = self._sell_units(request, curve0)
        open_units = self._open_units(request.mint)
        if open_units <= 0:
            raise await self._reject(
                request,
                request.decision_id,
                "no_position",
                f"mint={request.mint} sells need an open position",
                stage="ACCEPTED",
                source=ledger_source,
                correlation_id=correlation_id,
            )
        if units <= 0:
            raise await self._reject(
                request,
                request.decision_id,
                "below_liquidity_floor",
                f"T0={curve0.t_units} derived_units=0",
                stage="ACCEPTED",
                source=ledger_source,
                correlation_id=correlation_id,
            )
        if curve0.t_units < self._floor(units):
            raise await self._reject(
                request,
                request.decision_id,
                "below_liquidity_floor",
                f"T0={curve0.t_units} floor={self._floor(units)}",
                stage="ACCEPTED",
                source=ledger_source,
                correlation_id=correlation_id,
            )
        return units, min(units, self._fill_cap(curve0.t_units), open_units)

    async def _place_sell(
        self,
        request: OrderRequest,
        *,
        curve0: CurveSnapshot,
        ledger_source: str,
        correlation_id: str,
        seat: str | None,
        exit_reason: str | None,
        creator: str | None,
        owner: object,
    ) -> Fill:
        units, filled_units = await self._sell_targets(
            request, curve0, ledger_source=ledger_source, correlation_id=correlation_id
        )
        fraction = Decimal(filled_units) / Decimal(units)
        slippage_bps = self._slippage_bps(request)
        gross0 = sell_out(curve0.s_lamports, curve0.t_units, filled_units)
        out0 = gross0 - self._fees.venue_fee(gross0)
        threshold = out0 * (10_000 - slippage_bps) // 10_000
        order_id = self._ids.ulid()
        quote_id = self._ids.ulid()
        try:
            await self._append_order_batch(
                request,
                order_id=order_id,
                quote_id=quote_id,
                out0=out0,
                threshold=threshold,
                impact=impact_sell(curve0.t_units, filled_units),
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
        curve1, latency_s, _ = await self._await_confirmation(
            request,
            order_id=order_id,
            forbid_complete=False,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
            owner=owner,
        )
        state = self._fold_state()
        pos = state.positions.get(request.mint)
        held = pos.token_units if pos is not None and pos.token_units > 0 else 0
        if filled_units > held:
            # A concurrent exit committed first, or the holding was flattened: this
            # exit no longer fits the holding, so it is refused rather than clipped.
            self._inflight.discard(order_id)
            raise await self._reject(
                request,
                request.decision_id,
                "no_position",
                f"mint={request.mint} exit of {filled_units} exceeds holding {held} at CONFIRMING",
                stage="CONFIRMING",
                order_id=order_id,
                source=ledger_source,
                correlation_id=correlation_id,
            )
        gross1 = sell_out(curve1.s_lamports, curve1.t_units, filled_units)
        out1 = gross1 - self._fees.venue_fee(gross1)
        if out1 < threshold:
            self._inflight.discard(order_id)
            raise await self._reject(
                request,
                request.decision_id,
                "slippage_exceeded",
                f"confirm {out1} < threshold {threshold}",
                stage="CONFIRMING",
                order_id=order_id,
                quote_out=out0,
                threshold=threshold,
                confirm_out=out1,
                fees=self._fees.network_cost(),
                source=ledger_source,
                correlation_id=correlation_id,
            )
        network_cost = self._fees.network_cost()
        proceeds = out1 - network_cost
        price_avg = Decimal(gross1) / Decimal(filled_units)
        slipped = (out0 - out1) * 10_000 // out0 if out1 < out0 and out0 else 0
        venue_tx_ref = f"dry_run:{self._ids.ulid()}"
        closes = pos is not None and pos.token_units > 0 and filled_units >= pos.token_units
        rows: list[dict[str, Any]] = [
            {
                "ts_utc": self._now_ts(),
                "source": ledger_source,
                "correlation_id": correlation_id,
                "idempotency_key": f"fill|{order_id}",
                "type": "FillRecorded",
                "payload": {
                    "source": ledger_source,
                    "order_id": order_id,
                    "decision_id": request.decision_id,
                    "side": "sell",
                    "mint": request.mint,
                    "filled_lamports": proceeds,
                    "filled_units": filled_units,
                    "filled_fraction": str(fraction),
                    "price_avg": str(price_avg),
                    "venue_fee_lamports": self._fees.venue_fee(gross1),
                    "network_cost_lamports": network_cost,
                    "cash_delta_lamports": proceeds,
                    "latency_s": str(Decimal(str(latency_s))),
                    "venue_tx_ref": venue_tx_ref,
                    "curve_before_s": curve0.s_lamports,
                    "curve_before_t": curve0.t_units,
                    "curve_after_s": curve1.s_lamports,
                    "curve_after_t": curve1.t_units,
                    "route": "curve",
                    "realised_slippage_bps": slipped,
                },
            }
        ]
        if closes and pos is not None:
            realized = proceeds - int(pos.cost_basis_lamports)
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
            rows.append(
                {
                    "ts_utc": self._now_ts(),
                    "source": ledger_source,
                    "correlation_id": correlation_id,
                    "idempotency_key": f"close|{order_id}",
                    "type": "PositionClosed",
                    "payload": {
                        "source": ledger_source,
                        "mint": request.mint,
                        "price_exit": str(price_avg),
                        "proceeds_lamports": proceeds,
                        "realized_pnl_lamports": realized,
                        "reason": close_reason,
                        "pnl_pct": str(pnl_pct),
                        "hold_seconds": max(hold_s, 0),
                        "venue_tx_ref": venue_tx_ref,
                    },
                }
            )
        stored = self._store.append_batch(rows)
        self._inflight.discard(order_id)
        self._last_price_ts[request.mint] = self._clock.now()
        self._last_reserves[request.mint] = (curve1.s_lamports, curve1.t_units)
        return Fill(
            order_id=order_id,
            decision_id=request.decision_id,
            status=FillStatus.FILLED if filled_units == units else FillStatus.PARTIAL,
            venue_tx_ref=venue_tx_ref,
            filled_lamports=proceeds,
            filled_units=filled_units,
            filled_fraction=fraction,
            price_avg=price_avg,
            realised_slippage_bps=slipped,
            venue_fee_lamports=self._fees.venue_fee(gross1),
            network_cost_lamports=network_cost,
            route="curve",
            ledger_seq=int(stored[0]["seq"]),
        )
