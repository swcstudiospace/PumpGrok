"""SELL target sizing and settlement."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from pumpgrok.core.adapter import Fill, OrderRequest
from pumpgrok.core.errors import OrderRejectedError
from pumpgrok.execution.curve_math import impact_sell, sell_out
from pumpgrok.execution.paper_adapter.models import CurveSnapshot
from pumpgrok.execution.paper_adapter.sell_stages import SellPlan, _SellStagesMixin

if TYPE_CHECKING:
    from pumpgrok.core.ids import Clock, IdFactory
    from pumpgrok.execution.fees import FeeModel
    from pumpgrok.ledger.store import LedgerStore


class _SellMixin(_SellStagesMixin):
    if TYPE_CHECKING:
        _clock: Clock
        _fees: FeeModel
        _ids: IdFactory
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

    def _plan_sell(
        self,
        request: OrderRequest,
        curve0: CurveSnapshot,
        units: int,
        filled_units: int,
    ) -> SellPlan:
        """Decision-curve quote and the refusal threshold for one exit."""
        fraction = Decimal(filled_units) / Decimal(units)
        slippage_bps = self._slippage_bps(request)
        gross0 = sell_out(curve0.s_lamports, curve0.t_units, filled_units)
        out0 = gross0 - self._fees.venue_fee(gross0)
        threshold = out0 * (10_000 - slippage_bps) // 10_000
        order_id = self._ids.ulid()
        quote_id = self._ids.ulid()
        return SellPlan(
            units=units,
            filled_units=filled_units,
            fraction=fraction,
            out0=out0,
            threshold=threshold,
            impact=impact_sell(curve0.t_units, filled_units),
            order_id=order_id,
            quote_id=quote_id,
        )

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
        plan = self._plan_sell(request, curve0, units, filled_units)
        repeated = await self._submit_sell(
            request,
            plan,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
        )
        if repeated is not None:
            return repeated
        return await self._finish_sell(
            request,
            plan,
            curve0=curve0,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
            owner=owner,
        )
