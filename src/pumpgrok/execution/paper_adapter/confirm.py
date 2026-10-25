"""CONFIRMING latency, cancel, and re-check gate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.errors import OrderUnknownError
from pumpgrok.execution.latency import draw_latency
from pumpgrok.execution.paper_adapter.models import CurveSnapshot
from pumpgrok.tools.onchain.curve_layout import rpc_curve_price_allowed


class _ConfirmMixin:
    if TYPE_CHECKING:
        import random

        from pumpgrok.core.errors import OrderRejectedError
        from pumpgrok.core.ids import Clock
        from pumpgrok.execution.paper_adapter.models import _InflightOrders
        from pumpgrok.risk.engine import RiskEngine
        from pumpgrok.risk.limits import EngineLimits

        _cancelled: set[str]
        _clock: Clock
        _inflight: _InflightOrders
        _limits: EngineLimits
        _owned_order: dict[object, str]
        _p_drop: float
        _risk: RiskEngine
        _rng: random.Random

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
    ) -> tuple[CurveSnapshot, float, int | None]:
        """Latency sleep, cancel check, curve re-read, stop re-check, drop draw.

        Returns the CONFIRMING reserves, the virtual latency, and the trade size
        cap that CONFIRMING recomputed (None for sells). Any refusal
        discards the in-flight order and raises ``OrderRejectedError``; the
        caller compares the confirm-out against the decision threshold. When
        the latency sleep outlasts ``confirm_timeout_s`` the outcome is
        UNKNOWN: the placed row stays without an outcome, an
        ``OrderRejected`` row with reason ``confirmation_timeout`` is stored
        for repeat reconstruction, and ``OrderUnknownError`` is raised. The
        timed-out attempt is never retried (single-send rule).
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
        if order_id in self._cancelled:
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
        curve1 = await self._read_curve(request.mint)
        if curve1 is None:
            self._inflight.discard(order_id)
            raise await self._reject(
                request,
                request.decision_id,
                "no_reserves",
                f"mint={request.mint}",
                stage="CONFIRMING",
                order_id=order_id,
                source=ledger_source,
                correlation_id=correlation_id,
            )
        if request.side is Side.BUY and not rpc_curve_price_allowed(curve_source=curve1.source):
            self._inflight.discard(order_id)
            raise await self._reject(
                request,
                request.decision_id,
                "data_unavailable",
                f"curve layout {curve1.source} reads are ASSUMED",
                stage="CONFIRMING",
                order_id=order_id,
                source=ledger_source,
                correlation_id=correlation_id,
            )
        if forbid_complete and curve1.complete:
            self._inflight.discard(order_id)
            raise await self._reject(
                request,
                request.decision_id,
                "post_graduation_no_reserves",
                f"mint={request.mint} curve complete at CONFIRMING",
                stage="CONFIRMING",
                order_id=order_id,
                source=ledger_source,
                correlation_id=correlation_id,
            )
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
            self._inflight.discard(order_id)
            raise await self._reject(
                request,
                request.decision_id,
                recheck.reason,
                "CONFIRMING re-check",
                stage="CONFIRMING",
                order_id=order_id,
                source=ledger_source,
                correlation_id=correlation_id,
            )
        if dropped:
            self._inflight.discard(order_id)
            raise await self._reject(
                request,
                request.decision_id,
                "tx_dropped",
                "seeded drop; no retry",
                stage="CONFIRMING",
                order_id=order_id,
                source=ledger_source,
                correlation_id=correlation_id,
            )
        return (curve1, latency_s, recheck.size_lamports)
