"""Staged CONFIRMING checks: latency, cancel, curve re-read, stop re-check and drop."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.errors import OrderRejectedError, OrderUnknownError
from pumpgrok.execution.entry_hook import EntryDenied
from pumpgrok.execution.latency import draw_latency
from pumpgrok.execution.paper_adapter.models import CurveSnapshot
from pumpgrok.tools.onchain.curve_layout import rpc_curve_price_allowed

if TYPE_CHECKING:
    import random

    from pumpgrok.core.ids import Clock
    from pumpgrok.execution.paper_adapter.models import _InflightOrders
    from pumpgrok.risk.engine import RiskDecision, RiskEngine
    from pumpgrok.risk.limits import EngineLimits


class _ConfirmStagesMixin:
    if TYPE_CHECKING:
        _cancelled: set[str]
        _clock: Clock
        _inflight: _InflightOrders
        _limits: EngineLimits
        _owned_order: dict[object, str]
        _p_drop: float
        _risk: RiskEngine
        _rng: random.Random

        async def _read_curve(self, mint: str) -> CurveSnapshot | None: ...
        async def _read_entry_curve(self, mint: str) -> CurveSnapshot | None: ...

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

    async def _confirm_latency(
        self,
        request: OrderRequest,
        *,
        order_id: str,
        owner: object,
        ledger_source: str,
        correlation_id: str,
    ) -> tuple[float, bool]:
        """Register the order, draw its seeded latency and sleep it on virtual time.

        Returns ``(latency_s, dropped)``. An overrun leaves the outcome UNKNOWN.
        """
        self._owned_order[owner] = order_id
        self._inflight.add(order_id)
        latency_s, dropped = draw_latency(self._rng, p_drop=self._p_drop)
        try:
            async with self._clock.timeout(self._limits.confirm_timeout_s):
                await self._clock.sleep(latency_s)
        except TimeoutError:
            self._inflight.discard(order_id)
            await self._reject(
                request,
                request.decision_id,
                "confirmation_timeout",
                f"confirm wait {latency_s:.3f}s exceeded {self._limits.confirm_timeout_s:.3f}s",
                stage="CONFIRMING",
                order_id=order_id,
                source=ledger_source,
                correlation_id=correlation_id,
            )
            raise OrderUnknownError(
                "confirmation_timeout",
                f"order_id={order_id} outcome UNKNOWN; never retried",
                stage="CONFIRMING",
            ) from None
        return latency_s, dropped

    async def _confirm_refuse(
        self,
        request: OrderRequest,
        *,
        order_id: str,
        reason: str,
        detail: str,
        ledger_source: str,
        correlation_id: str,
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
            source=ledger_source,
            correlation_id=correlation_id,
        )

    async def _confirm_cancel_check(
        self,
        request: OrderRequest,
        *,
        order_id: str,
        ledger_source: str,
        correlation_id: str,
    ) -> None:
        """A cancel that landed during the latency sleep refuses the order."""
        if order_id not in self._cancelled:
            return
        self._inflight.discard(order_id)
        self._cancelled.discard(order_id)
        raise await self._reject(
            request,
            request.decision_id,
            "cancelled",
            f"order_id={order_id}",
            stage="CONFIRMING",
            order_id=order_id,
            source=ledger_source,
            correlation_id=correlation_id,
        )

    async def _confirm_curve(
        self,
        request: OrderRequest,
        *,
        order_id: str,
        forbid_complete: bool,
        ledger_source: str,
        correlation_id: str,
    ) -> CurveSnapshot:
        """Re-read the curve at CONFIRMING, then apply the layout and graduation gates."""
        if request.side is Side.BUY:
            try:
                curve1 = await self._read_entry_curve(request.mint)
            except EntryDenied as denied:
                raise await self._confirm_refuse(
                    request,
                    order_id=order_id,
                    reason="data_unavailable",
                    detail=denied.detail,
                    ledger_source=ledger_source,
                    correlation_id=correlation_id,
                ) from None
        else:
            curve1 = await self._read_curve(request.mint)
        if curve1 is None:
            raise await self._confirm_refuse(
                request,
                order_id=order_id,
                reason="no_reserves",
                detail=f"mint={request.mint}",
                ledger_source=ledger_source,
                correlation_id=correlation_id,
            )
        if request.side is Side.BUY and not rpc_curve_price_allowed(curve_source=curve1.source):
            raise await self._confirm_refuse(
                request,
                order_id=order_id,
                reason="data_unavailable",
                detail=f"curve layout {curve1.source} reads are ASSUMED",
                ledger_source=ledger_source,
                correlation_id=correlation_id,
            )
        if forbid_complete and curve1.complete:
            raise await self._confirm_refuse(
                request,
                order_id=order_id,
                reason="post_graduation_no_reserves",
                detail=f"mint={request.mint} curve complete at CONFIRMING",
                ledger_source=ledger_source,
                correlation_id=correlation_id,
            )
        return curve1

    async def _confirm_recheck(
        self,
        request: OrderRequest,
        *,
        order_id: str,
        dropped: bool,
        seat: str | None,
        exit_reason: str | None,
        creator: str | None,
        ledger_source: str,
        correlation_id: str,
    ) -> RiskDecision:
        """Stop and risk checks on the CONFIRMING reserves, then the seeded drop."""
        recheck = self._risk.check(
            request,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
            source=ledger_source,
            correlation_id=correlation_id,
            stage="CONFIRMING",
        )
        if not recheck.passed:
            raise await self._confirm_refuse(
                request,
                order_id=order_id,
                reason=recheck.reason,
                detail="CONFIRMING re-check",
                ledger_source=ledger_source,
                correlation_id=correlation_id,
            )
        if dropped:
            raise await self._confirm_refuse(
                request,
                order_id=order_id,
                reason="tx_dropped",
                detail="seeded drop; no retry",
                ledger_source=ledger_source,
                correlation_id=correlation_id,
            )
        return recheck
