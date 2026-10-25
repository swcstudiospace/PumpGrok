"""Order placement and the BUY pipeline."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal

from pumpgrok.core.adapter import Fill, FillStatus, OrderRequest, Side
from pumpgrok.core.errors import OrderRejectedError
from pumpgrok.core.idempotency import exec_place_key
from pumpgrok.execution.curve_math import buy_out, impact_buy
from pumpgrok.execution.paper_adapter.models import CurveSnapshot, _BuyConfirmed, _BuyQuote
from pumpgrok.risk.engine import RiskDecision, order_hash_for
from pumpgrok.tools.onchain.curve_layout import rpc_curve_price_allowed

if TYPE_CHECKING:
    from pumpgrok.core.ids import Clock, IdFactory
    from pumpgrok.execution.fees import FeeModel
    from pumpgrok.execution.paper_adapter.models import _InflightOrders
    from pumpgrok.ledger.store import LedgerStore
    from pumpgrok.risk.engine import RiskEngine


class _BuyMixin:
    if TYPE_CHECKING:
        _active_places: set[str]
        _clock: Clock
        _fees: FeeModel
        _ids: IdFactory
        _inflight: _InflightOrders
        _last_price_ts: dict[str, float]
        _last_reserves: dict[str, tuple[int, int]]
        _owned_order: dict[object, str]
        _risk: RiskEngine
        _source: Literal["paper", "replay", "manual"]
        _store: LedgerStore

        def _fold_state(self) -> Any: ...

        def _now_ts(self) -> str: ...

        def _fill_cap(self, s_lamports: int) -> int: ...

        def _floor(self, size_lamports: int) -> int: ...

        def _slippage_bps(self, request: OrderRequest) -> int: ...

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
        ) -> Fill: ...

    async def place(
        self,
        request: OrderRequest,
        *,
        seat: str | None = None,
        exit_reason: str | None = None,
        creator: str | None = None,
        source: str | None = None,
        correlation_id: str = "desk",
    ) -> Fill:
        """Place one order; its breaker probe is released on every final outcome.

        A fill resolves the probe as success; a refusal, confirmation timeout or
        cancel resolves it as failure. A concurrent repeat of an in-flight
        decision leaves the probe to its owner. Orders without a probe are
        untouched.
        """
        if exit_reason is None:
            exit_reason = request.exit_reason
        ledger_source = source if source is not None else self._source
        order_hash = order_hash_for(request)
        key = exec_place_key(request.ticket_id, request.side.value, request.decision_id)
        # One token per call: a call only ever clears the barrier entry it registered.
        owner = object()
        owns_key = key not in self._active_places
        if owns_key:
            self._active_places.add(key)
        try:
            fill = await self._place_order(
                request,
                seat=seat,
                exit_reason=exit_reason,
                creator=creator,
                source=source,
                correlation_id=correlation_id,
                owner=owner,
            )
        except BaseException:
            self._settle_probes(
                order_hash, owner, key, False, source=ledger_source, correlation_id=correlation_id
            )
            raise
        else:
            self._settle_probes(
                order_hash, owner, key, True, source=ledger_source, correlation_id=correlation_id
            )
            return fill
        finally:
            if owns_key:
                self._active_places.discard(key)
            self._clear_owned(owner)

    def _settle_probes(
        self,
        order_hash: str,
        owner: object,
        key: str,
        ok: bool,
        *,
        source: str,
        correlation_id: str,
    ) -> None:
        """Release the breaker probe at this call's final outcome, when this call settles it.

        A call settles the order it wrote (its token is in ``_owned_order``). A call that
        refused before any write settles only when no order was written for the decision.
        A call that lost the write race (``in_flight``, or a repeat of an order another
        call placed) leaves the probe to the call that placed it, so it is not released
        while that order is still in flight.
        """
        settles = owner in self._owned_order or self._store.by_key(key) is None
        if settles:
            self._risk.release_order_probes(
                order_hash, ok, source=source, correlation_id=correlation_id
            )

    def _clear_owned(self, owner: object) -> None:
        """Remove the barrier entry this call registered, if any; idempotent."""
        order_id = self._owned_order.pop(owner, None)
        if order_id is not None:
            self._inflight.discard(order_id)

    async def _order_risk_decision(
        self,
        request: OrderRequest,
        *,
        seat: str | None,
        exit_reason: str | None,
        creator: str | None,
        ledger_source: str,
        correlation_id: str,
    ) -> RiskDecision:
        """ACCEPTED risk gate bound to this order; refused orders raise here."""
        order_hash = order_hash_for(request)
        decision = self._risk.check(
            request,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
            source=ledger_source,
            correlation_id=correlation_id,
            stage="ACCEPTED",
        )
        if decision.order_hash != order_hash:
            raise RuntimeError("risk decision is not bound to this order")
        if not decision.passed:
            raise await self._reject(
                request,
                decision.decision_id,
                decision.reason,
                "risk refused",
                stage="ACCEPTED",
                source=ledger_source,
                correlation_id=correlation_id,
            )
        return decision

    async def _order_curve(
        self,
        request: OrderRequest,
        *,
        ledger_source: str,
        correlation_id: str,
    ) -> CurveSnapshot:
        """Decision reserves with the ACCEPTED entry gates; refusals raise here."""
        curve0 = await self._read_curve(request.mint)
        if curve0 is None:
            raise await self._reject(
                request,
                request.decision_id,
                "no_reserves",
                f"mint={request.mint}",
                stage="ACCEPTED",
                source=ledger_source,
                correlation_id=correlation_id,
            )
        # The source gate prices entries only: a stop-loss sell must still fill (INV-R-16).
        if request.side is Side.BUY and not rpc_curve_price_allowed(curve_source=curve0.source):
            raise await self._reject(
                request,
                request.decision_id,
                "data_unavailable",
                f"curve layout {curve0.source} reads are ASSUMED",
                stage="ACCEPTED",
                source=ledger_source,
                correlation_id=correlation_id,
            )
        if curve0.complete:
            raise await self._reject(
                request,
                request.decision_id,
                "post_graduation_no_reserves",
                f"mint={request.mint} curve complete",
                stage="ACCEPTED",
                source=ledger_source,
                correlation_id=correlation_id,
            )
        return curve0

    async def _place_order(
        self,
        request: OrderRequest,
        *,
        seat: str | None = None,
        exit_reason: str | None = None,
        creator: str | None = None,
        source: str | None = None,
        correlation_id: str = "desk",
        owner: object,
    ) -> Fill:
        """Risk, batch, latency, CONFIRMING re-check, then a curve-priced fill."""
        ledger_source = source if source is not None else self._source
        repeated = self._repeat_outcome(request)
        if repeated is not None:
            if isinstance(repeated, Fill):
                return repeated
            raise repeated
        decision = await self._order_risk_decision(
            request,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
        )
        curve0 = await self._order_curve(
            request,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
        )
        if request.side is Side.BUY:
            return await self._place_buy(
                request,
                decision_size=int(decision.size_lamports or 0),
                curve0=curve0,
                ledger_source=ledger_source,
                correlation_id=correlation_id,
                seat=seat,
                exit_reason=exit_reason,
                creator=creator,
                owner=owner,
            )
        return await self._place_sell(
            request,
            curve0=curve0,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
            owner=owner,
        )

    async def _buy_sizing(
        self,
        request: OrderRequest,
        *,
        decision_size: int,
        curve0: CurveSnapshot,
        ledger_source: str,
        correlation_id: str,
    ) -> _BuyQuote:
        """Liquidity floor plus the decision-reserve fill math; refusals raise here."""
        size = decision_size
        if curve0.s_lamports < self._floor(size):
            raise await self._reject(
                request,
                request.decision_id,
                "below_liquidity_floor",
                f"S0={curve0.s_lamports} floor={self._floor(size)}",
                stage="ACCEPTED",
                source=ledger_source,
                correlation_id=correlation_id,
            )
        filled = min(size, self._fill_cap(curve0.s_lamports))
        fraction = Decimal(filled) / Decimal(size)
        venue_fee = self._fees.venue_fee(filled)
        x_net = filled - venue_fee
        slippage_bps = self._slippage_bps(request)
        out0 = buy_out(curve0.s_lamports, curve0.t_units, x_net)
        threshold = out0 * (10_000 - slippage_bps) // 10_000
        return _BuyQuote(
            size=size,
            filled=filled,
            fraction=fraction,
            venue_fee=venue_fee,
            x_net=x_net,
            slippage_bps=slippage_bps,
            out0=out0,
            threshold=threshold,
        )

    async def _buy_append_batch(
        self,
        request: OrderRequest,
        *,
        quote: _BuyQuote,
        curve0: CurveSnapshot,
        ledger_source: str,
        correlation_id: str,
        seat: str | None,
        exit_reason: str | None,
        creator: str | None,
    ) -> Fill | tuple[str, str]:
        """Write the ACCEPTED batch; a repeated decision returns its first Fill."""
        order_id = self._ids.ulid()
        quote_id = self._ids.ulid()
        try:
            await self._append_order_batch(
                request,
                order_id=order_id,
                quote_id=quote_id,
                out0=quote.out0,
                threshold=quote.threshold,
                impact=impact_buy(curve0.s_lamports, quote.filled),
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
        return (order_id, quote_id)

    async def _buy_confirm(
        self,
        request: OrderRequest,
        *,
        quote: _BuyQuote,
        curve0: CurveSnapshot,
        order_id: str,
        ledger_source: str,
        correlation_id: str,
        seat: str | None,
        exit_reason: str | None,
        creator: str | None,
        owner: object,
    ) -> _BuyConfirmed:
        """CONFIRMING re-check, cap recompute, and confirm-reserve pricing."""
        curve1, latency_s, cap_now = await self._await_confirmation(
            request,
            order_id=order_id,
            forbid_complete=True,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
            owner=owner,
        )
        filled = quote.filled
        fraction = quote.fraction
        venue_fee = quote.venue_fee
        x_net = quote.x_net
        out0 = quote.out0
        threshold = quote.threshold
        if cap_now is not None and cap_now < filled:
            # CONFIRMING recomputed a smaller trade cap during the wait: fill only
            # up to it, priced at the decision reserves with a threshold to match.
            filled = cap_now
            fraction = Decimal(filled) / Decimal(quote.size)
            venue_fee = self._fees.venue_fee(filled)
            x_net = filled - venue_fee
            out0 = buy_out(curve0.s_lamports, curve0.t_units, x_net)
            threshold = out0 * (10_000 - quote.slippage_bps) // 10_000
        out1 = buy_out(curve1.s_lamports, curve1.t_units, x_net)
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
        return _BuyConfirmed(
            curve1=curve1,
            latency_s=latency_s,
            filled=filled,
            fraction=fraction,
            venue_fee=venue_fee,
            x_net=x_net,
            out0=out0,
            threshold=threshold,
            out1=out1,
        )

    def _buy_fill_rows(
        self,
        request: OrderRequest,
        *,
        order_id: str,
        venue_tx_ref: str,
        ledger_source: str,
        correlation_id: str,
        creator: str | None,
        curve0: CurveSnapshot,
        confirmed: _BuyConfirmed,
        price_avg: Decimal,
        network_cost: int,
        cash_debit: int,
        slipped: int,
        had_position: bool,
    ) -> list[dict[str, Any]]:
        """FillRecorded plus PositionOpened rows for a confirmed BUY."""
        curve1 = confirmed.curve1
        latency_s = confirmed.latency_s
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
                    "side": "buy",
                    "mint": request.mint,
                    "filled_lamports": confirmed.filled,
                    "filled_units": confirmed.out1,
                    "filled_fraction": str(confirmed.fraction),
                    "price_avg": str(price_avg),
                    "venue_fee_lamports": confirmed.venue_fee,
                    "network_cost_lamports": network_cost,
                    "cash_delta_lamports": -cash_debit,
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
        if not had_position:
            rows.append(
                {
                    "ts_utc": self._now_ts(),
                    "source": ledger_source,
                    "correlation_id": correlation_id,
                    "idempotency_key": f"position|{order_id}",
                    "type": "PositionOpened",
                    "payload": {
                        "source": ledger_source,
                        "mint": request.mint,
                        "price_entry": str(price_avg),
                        "token_units": confirmed.out1,
                        "cost_basis_lamports": cash_debit,
                        "opened_ts_utc": self._now_ts(),
                        "symbol": "",
                        "creator": creator or "",
                        "ticket_id": request.ticket_id,
                        "score": "0",
                    },
                }
            )
        return rows

    async def _buy_settle(
        self,
        request: OrderRequest,
        *,
        quote: _BuyQuote,
        confirmed: _BuyConfirmed,
        curve0: CurveSnapshot,
        ledger_source: str,
        correlation_id: str,
        creator: str | None,
        order_id: str,
    ) -> Fill:
        """Ledger append and Fill for a confirmed BUY."""
        network_cost = self._fees.network_cost()
        cash_debit = confirmed.filled + network_cost
        price_avg = Decimal(confirmed.x_net) / Decimal(confirmed.out1)
        slipped = (
            (confirmed.out0 - confirmed.out1) * 10_000 // confirmed.out0
            if confirmed.out1 < confirmed.out0 and confirmed.out0
            else 0
        )
        venue_tx_ref = f"dry_run:{self._ids.ulid()}"
        state = self._fold_state()
        had_position = (
            state.positions.get(request.mint) is not None
            and state.positions[request.mint].token_units > 0
        )
        rows = self._buy_fill_rows(
            request,
            order_id=order_id,
            venue_tx_ref=venue_tx_ref,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
            creator=creator,
            curve0=curve0,
            confirmed=confirmed,
            price_avg=price_avg,
            network_cost=network_cost,
            cash_debit=cash_debit,
            slipped=slipped,
            had_position=had_position,
        )
        stored = self._store.append_batch(rows)
        self._inflight.discard(order_id)
        self._last_price_ts[request.mint] = self._clock.now()
        self._last_reserves[request.mint] = (
            confirmed.curve1.s_lamports,
            confirmed.curve1.t_units,
        )
        return Fill(
            order_id=order_id,
            decision_id=request.decision_id,
            status=FillStatus.FILLED if confirmed.filled == quote.size else FillStatus.PARTIAL,
            venue_tx_ref=venue_tx_ref,
            filled_lamports=confirmed.filled,
            filled_units=confirmed.out1,
            filled_fraction=confirmed.fraction,
            price_avg=price_avg,
            realised_slippage_bps=slipped,
            venue_fee_lamports=confirmed.venue_fee,
            network_cost_lamports=network_cost,
            route="curve",
            ledger_seq=int(stored[0]["seq"]),
        )

    async def _place_buy(
        self,
        request: OrderRequest,
        *,
        decision_size: int,
        curve0: CurveSnapshot,
        ledger_source: str,
        correlation_id: str,
        seat: str | None,
        exit_reason: str | None,
        creator: str | None,
        owner: object,
    ) -> Fill:
        quote = await self._buy_sizing(
            request,
            decision_size=decision_size,
            curve0=curve0,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
        )
        placed = await self._buy_append_batch(
            request,
            quote=quote,
            curve0=curve0,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
        )
        if isinstance(placed, Fill):
            return placed
        order_id, _ = placed
        confirmed = await self._buy_confirm(
            request,
            quote=quote,
            curve0=curve0,
            order_id=order_id,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
            owner=owner,
        )
        return await self._buy_settle(
            request,
            quote=quote,
            confirmed=confirmed,
            curve0=curve0,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
            creator=creator,
            order_id=order_id,
        )
