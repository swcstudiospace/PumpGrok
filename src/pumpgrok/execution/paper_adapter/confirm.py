"""CONFIRMING latency, cancel, and re-check gate."""

from __future__ import annotations

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.execution.paper_adapter.confirm_stages import _ConfirmStagesMixin
from pumpgrok.execution.paper_adapter.models import CurveSnapshot


class _ConfirmMixin(_ConfirmStagesMixin):
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
        latency_s, dropped = await self._confirm_latency(
            request,
            order_id=order_id,
            owner=owner,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
        )
        await self._confirm_cancel_check(
            request, order_id=order_id, ledger_source=ledger_source, correlation_id=correlation_id
        )
        curve1 = await self._confirm_curve(
            request,
            order_id=order_id,
            forbid_complete=forbid_complete,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
        )
        recheck = await self._confirm_recheck(
            request,
            order_id=order_id,
            dropped=dropped,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
        )
        return (curve1, latency_s, recheck.size_lamports)
