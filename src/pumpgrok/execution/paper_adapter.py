"""Curve-faithful paper fills (paper-engine.md 2, PAPER-001, PAPER-005, R6, R38).

Every pre-graduation fill prices from curve reserves, never from a quote.
The Jupiter quote is informational only: it is stored on ``OrderPlaced``
with ``source="curve"`` and never enters the fill math (T-04-08).

One order flows NEW -> ACCEPTED -> CONFIRMING -> FILLED | PARTIAL |
REJECTED (paper-engine.md 2.8). ``RiskEngine.check`` runs first with the
order hash bound (R24); no fill exists without a passing ``RiskDecision``.
``OrderPlaced`` shares one ``append_batch`` transaction with the approval
consumption row (the shared-transaction shape; autonomous-mint persistence
lands in plan 04-07). Seeded confirmation latency runs on the injected
clock; CONFIRMING re-reads the curve and re-runs the stop checks before
any fill is computed. Idempotency is on ``(ticket_id, side, decision_id)``
(R23): a repeated decision returns the first Fill.
"""

from __future__ import annotations

import random
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from pumpgrok.core.adapter import (
    ExecutionAdapter,
    ExecutionMode,
    Fill,
    FillStatus,
    OrderRequest,
    Position,
    Quote,
    Side,
    SimulationResult,
)
from pumpgrok.core.errors import OrderRejectedError, OrderUnknownError
from pumpgrok.core.idempotency import canonical_json, exec_place_key
from pumpgrok.core.ids import Clock, IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.curve_math import buy_out, impact_buy, impact_sell, sell_out, spot
from pumpgrok.execution.fees import FeeModel
from pumpgrok.execution.latency import P_DROP, draw_latency
from pumpgrok.ledger.reducer import PositionView, initial_state, reduce
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import format_ts_utc, parse_ts_utc
from pumpgrok.risk.engine import SYSTEM_EXIT_REASONS, RiskEngine, order_hash_for
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.tools.onchain.curve_layout import rpc_curve_price_allowed

__all__ = [
    "CurveSnapshot",
    "OrderRejectedError",
    "OrderUnknownError",
    "PaperAdapter",
    "PriceSource",
]


class CurveSnapshot(BaseModel):
    """Reserves observed at one instant. Integers; ratios stay Decimal."""

    model_config = ConfigDict(frozen=True)

    mint: str
    s_lamports: int
    t_units: int
    complete: bool = False
    source: str = "fixture"
    slot: int | None = None


class PriceSource(Protocol):
    """Curve reads. Live-paper binds RPC/REST; replay binds fixture ticks."""

    async def curve(self, mint: str) -> CurveSnapshot | None: ...


def _rejection_from_row(
    stored: Mapping[str, Any], *, fallback: OrderRejectedError
) -> OrderRejectedError:
    """Rebuild the refusal recorded in a stored ``OrderRejected`` row.

    A ``confirmation_timeout`` row maps to ``OrderUnknownError`` (the timed-out
    attempt is never retried); every other reason maps to the documented
    ``OrderRejectedError``. Unparseable rows fall back to the live error.
    """
    payload = stored.get("payload", {})
    if not isinstance(payload, dict):
        return fallback
    reason = str(payload.get("reason", fallback.reason))
    detail = str(payload.get("detail", fallback.detail))
    stage = str(payload.get("stage", fallback.stage))
    fees = payload.get("fees_lamports", fallback.fees_lamports)
    try:
        fees_lamports = int(fees)
    except (TypeError, ValueError):
        fees_lamports = fallback.fees_lamports
    if reason == "confirmation_timeout":
        return OrderUnknownError(reason, detail, stage=stage, fees_lamports=fees_lamports)
    return OrderRejectedError(reason, detail, stage=stage, fees_lamports=fees_lamports)


class PaperAdapter(ExecutionAdapter):
    """Paper fills from curve reserves with risk in process (R24)."""

    mode = ExecutionMode.PAPER
    venue = "paper"

    def __init__(
        self,
        *,
        store: LedgerStore,
        risk: RiskEngine,
        ids: IdFactory,
        clock: Clock,
        rng: random.Random,
        budget: RiskBudget | None = None,
        limits: EngineLimits | None = None,
        fees: FeeModel | None = None,
        price_source: PriceSource | None = None,
        source: Literal["paper", "replay", "manual"] = "paper",
        curve_origin: str = "fixture",
        p_drop: float = P_DROP,
    ) -> None:
        self._store = store
        self._risk = risk
        self._ids = ids
        self._clock = clock
        self._rng = rng
        self._budget = budget if budget is not None else RiskBudget()
        self._limits = limits if limits is not None else EngineLimits()
        self._fees = fees if fees is not None else FeeModel()
        self._price = price_source
        self._source = source
        self._curve_origin = curve_origin
        self._p_drop = p_drop
        self._inflight: set[str] = set()
        self._cancelled: set[str] = set()
        self._last_price_ts: dict[str, float] = {}
        self._last_reserves: dict[str, tuple[int, int]] = {}
        self._frozen_marks: dict[str, int] = {}

    # -- read-only helpers -------------------------------------------------

    def _now_ts(self) -> str:
        return format_ts_utc(self._clock.now())

    def _fold_state(self) -> Any:
        meta_equity = self._store.get_meta("initial_equity_lamports")
        initial = (
            int(meta_equity) if meta_equity is not None else self._budget.paper_equity_lamports
        )
        state = initial_state(
            source=self._source,
            initial_equity_lamports=initial,
            day_utc=format_ts_utc(self._clock.now())[:10],
        )
        for event in self._store.read(limit=None):
            state = reduce(state, event)
        return state

    def _fill_cap(self, s_lamports: int) -> int:
        return int(Decimal(s_lamports) * self._budget.partial_fill_fraction)

    def _floor(self, size_lamports: int) -> int:
        return int(self._budget.liquidity_floor_multiple) * size_lamports

    def _slippage_bps(self, request: OrderRequest) -> int:
        return min(int(request.max_slippage_bps), int(self._limits.max_slippage_bps))

    @staticmethod
    def _sell_units(request: OrderRequest, curve: CurveSnapshot) -> int:
        """Token units for a sell: carried units, else SOL notional at the curve.
        Size-based sells (the CLI sell path, ``human_sell`` approvals) carry
        ``size_lamports`` without ``token_units``; units derive here at the
        decision curve as ``size * T // S`` (floored, never negative).
        """
        return PaperAdapter._sell_preview_units(request.size_lamports, request.token_units, curve)

    @staticmethod
    def _sell_preview_units(
        size_lamports: int | None, token_units: int | None, curve: CurveSnapshot
    ) -> int:
        """Unit derivation shared by ``_sell_units`` and the fill preview."""
        if token_units is not None:
            return int(token_units)
        size = int(size_lamports or 0)
        if size <= 0 or curve.s_lamports <= 0:
            return 0
        return size * curve.t_units // curve.s_lamports

    def _open_units(self, mint: str) -> int:
        """Open token units for ``mint`` from the ledger fold; zero when flat."""
        pos = self._fold_state().positions.get(mint)
        if pos is None:
            return 0
        return int(pos.token_units)

    def cash_lamports(self) -> int:
        """Spendable paper cash from the ledger fold (exec.positions)."""
        return int(self._fold_state().cash_lamports)

    def equity_lamports(self) -> int:
        """Cash plus open-position marks from the ledger fold (exec.positions)."""
        state = self._fold_state()
        return int(state.cash_lamports) + sum(
            int(pos.last_mtm_lamports) for pos in state.positions.values() if pos.token_units > 0
        )

    # -- ExecutionAdapter: quote / simulate --------------------------------

    async def quote(
        self, input_mint: str, output_mint: str, amount: int, slippage_bps: int
    ) -> Quote:
        """Buy-direction curve quote: ``amount`` lamports in, token units out."""
        curve = await self._read_curve(output_mint)
        if curve is None:
            raise OrderRejectedError("no_reserves", f"mint={output_mint}", stage="ACCEPTED")
        out_amount = buy_out(curve.s_lamports, curve.t_units, amount)
        threshold = out_amount * (10_000 - slippage_bps) // 10_000
        return Quote(
            quote_id=self._ids.ulid(),
            in_amount=amount,
            out_amount=out_amount,
            other_amount_threshold=threshold,
            price_impact_pct=impact_buy(curve.s_lamports, amount),
            route_plan=[{"venue": "curve", "mint": output_mint}],
            context_slot=curve.slot,
            source="curve",
            expires_at=datetime.fromtimestamp(self._clock.now() + 60.0, UTC),
        )

    async def simulate(
        self,
        *,
        mint: str,
        side: Side,
        size_lamports: int | None,
        token_units: int | None,
    ) -> SimulationResult:
        """Pure-math preview: no risk check, no latency, no ledger writes."""
        curve = await self._read_curve(mint)
        if curve is None:
            return SimulationResult(
                would_fill=False,
                fill_kind="rejected",
                price_expected=Decimal("0"),
                expected_out=0,
                price_impact_pct=Decimal("0"),
                venue_fee_lamports=0,
                network_cost_lamports=self._fees.network_cost(),
                liquidity_ratio=Decimal("0"),
                rejection_reason="no_reserves",
                latency_ms_estimate=1200,
            )
        if side is Side.BUY:
            size = int(size_lamports or 0)
            if curve.s_lamports < self._floor(size):
                return self._sim_reject("below_liquidity_floor", curve.s_lamports, size)
            filled = min(size, self._fill_cap(curve.s_lamports))
            out = buy_out(curve.s_lamports, curve.t_units, filled - self._fees.venue_fee(filled))
            return SimulationResult(
                would_fill=True,
                fill_kind="full" if filled == size else "partial",
                price_expected=spot(curve.s_lamports, curve.t_units),
                expected_out=out,
                price_impact_pct=impact_buy(curve.s_lamports, filled),
                venue_fee_lamports=self._fees.venue_fee(filled),
                network_cost_lamports=self._fees.network_cost(),
                liquidity_ratio=Decimal(curve.s_lamports) / Decimal(size),
                rejection_reason=None,
                latency_ms_estimate=1200,
            )
        units = self._sell_preview_units(size_lamports, token_units, curve)
        if units <= 0:
            return self._sim_reject("below_liquidity_floor", curve.t_units, units)
        if curve.t_units < self._floor(units):
            return self._sim_reject("below_liquidity_floor", curve.t_units, units)
        filled_units = min(units, self._fill_cap(curve.t_units))
        gross = sell_out(curve.s_lamports, curve.t_units, filled_units)
        return SimulationResult(
            would_fill=True,
            fill_kind="full" if filled_units == units else "partial",
            price_expected=spot(curve.s_lamports, curve.t_units),
            expected_out=gross - self._fees.venue_fee(gross),
            price_impact_pct=impact_sell(curve.t_units, filled_units),
            venue_fee_lamports=self._fees.venue_fee(gross),
            network_cost_lamports=self._fees.network_cost(),
            liquidity_ratio=Decimal(curve.t_units) / Decimal(units),
            rejection_reason=None,
            latency_ms_estimate=1200,
        )

    def _sim_reject(self, reason: str, reserve: int, size: int) -> SimulationResult:
        return SimulationResult(
            would_fill=False,
            fill_kind="rejected",
            price_expected=Decimal("0"),
            expected_out=0,
            price_impact_pct=Decimal("0"),
            venue_fee_lamports=0,
            network_cost_lamports=self._fees.network_cost(),
            liquidity_ratio=Decimal(reserve) / Decimal(size) if size else Decimal("0"),
            rejection_reason=reason,
            latency_ms_estimate=1200,
        )

    # -- ExecutionAdapter: place -------------------------------------------

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
        cancel resolves it as failure. Orders without a probe are untouched.
        """
        ledger_source = source if source is not None else self._source
        order_hash = order_hash_for(request)
        try:
            fill = await self._place_order(
                request,
                seat=seat,
                exit_reason=exit_reason,
                creator=creator,
                source=source,
                correlation_id=correlation_id,
            )
        except BaseException:
            self._risk.release_order_probes(
                order_hash, False, source=ledger_source, correlation_id=correlation_id
            )
            raise
        self._risk.release_order_probes(
            order_hash, True, source=ledger_source, correlation_id=correlation_id
        )
        return fill

    async def _place_order(
        self,
        request: OrderRequest,
        *,
        seat: str | None = None,
        exit_reason: str | None = None,
        creator: str | None = None,
        source: str | None = None,
        correlation_id: str = "desk",
    ) -> Fill:
        """Risk, batch, latency, CONFIRMING re-check, then a curve-priced fill."""
        ledger_source = source if source is not None else self._source
        repeated = self._repeat_outcome(request)
        if repeated is not None:
            if isinstance(repeated, Fill):
                return repeated
            raise repeated
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
        if not rpc_curve_price_allowed(curve_source=self._curve_origin):
            raise await self._reject(
                request,
                request.decision_id,
                "data_unavailable",
                f"curve layout {self._curve_origin} reads are ASSUMED",
                stage="ACCEPTED",
                source=ledger_source,
                correlation_id=correlation_id,
            )
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
            )
        return await self._place_sell(
            request,
            curve0=curve0,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
        )

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
    ) -> tuple[CurveSnapshot, float]:
        """Latency sleep, cancel check, curve re-read, stop re-check, drop draw.

        Returns the CONFIRMING reserves with the virtual latency. Any refusal
        discards the in-flight order and raises ``OrderRejectedError``; the
        caller compares the confirm-out against the decision threshold. When
        the latency sleep outlasts ``confirm_timeout_s`` the outcome is
        UNKNOWN: the placed row stays without an outcome, an
        ``OrderRejected`` row with reason ``confirmation_timeout`` is stored
        for repeat reconstruction, and ``OrderUnknownError`` is raised. The
        timed-out attempt is never retried (single-send rule).
        """
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
        return (curve1, latency_s)

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
    ) -> Fill:
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
        order_id = self._ids.ulid()
        quote_id = self._ids.ulid()
        try:
            await self._append_order_batch(
                request,
                order_id=order_id,
                quote_id=quote_id,
                out0=out0,
                threshold=threshold,
                impact=impact_buy(curve0.s_lamports, filled),
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
        curve1, latency_s = await self._await_confirmation(
            request,
            order_id=order_id,
            forbid_complete=True,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
        )
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
        network_cost = self._fees.network_cost()
        cash_debit = filled + network_cost
        price_avg = Decimal(x_net) / Decimal(out1)
        slipped = (out0 - out1) * 10_000 // out0 if out1 < out0 and out0 else 0
        venue_tx_ref = f"dry_run:{self._ids.ulid()}"
        state = self._fold_state()
        had_position = (
            state.positions.get(request.mint) is not None
            and state.positions[request.mint].token_units > 0
        )
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
                    "filled_lamports": filled,
                    "filled_units": out1,
                    "filled_fraction": str(fraction),
                    "price_avg": str(price_avg),
                    "venue_fee_lamports": venue_fee,
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
                        "token_units": out1,
                        "cost_basis_lamports": cash_debit,
                        "opened_ts_utc": self._now_ts(),
                        "symbol": "",
                        "creator": creator or "",
                        "ticket_id": request.ticket_id,
                        "score": "0",
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
            status=FillStatus.FILLED if filled == size else FillStatus.PARTIAL,
            venue_tx_ref=venue_tx_ref,
            filled_lamports=filled,
            filled_units=out1,
            filled_fraction=fraction,
            price_avg=price_avg,
            realised_slippage_bps=slipped,
            venue_fee_lamports=venue_fee,
            network_cost_lamports=network_cost,
            route="curve",
            ledger_seq=int(stored[0]["seq"]),
        )

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
        curve1, latency_s = await self._await_confirmation(
            request,
            order_id=order_id,
            forbid_complete=False,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
            seat=seat,
            exit_reason=exit_reason,
            creator=creator,
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
        state = self._fold_state()
        pos = state.positions.get(request.mint)
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

    # -- order batch, rejects, repeats -------------------------------------

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
            and approval.approved_by != "risk_engine"
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

    async def _read_curve(self, mint: str) -> CurveSnapshot | None:
        if self._price is None:
            return None
        return await self._price.curve(mint)

    # -- ExecutionAdapter: cancel / positions -------------------------------

    async def cancel(self, order_id: str, ticket_id: str, decision_id: str) -> bool:
        """Cancel while ACCEPTED; False once the latency sleep has completed."""
        if order_id not in self._inflight:
            return False
        self._cancelled.add(order_id)
        return True

    async def positions(self, mint: str | None = None) -> Sequence[Position]:
        """Open positions from the ledger fold (04-07 wires this to exec)."""
        state = self._fold_state()
        out: list[Position] = []
        for key, view in state.positions.items():
            if view.token_units <= 0:
                continue
            if mint is not None and key != mint:
                continue
            try:
                opened_at = datetime.fromisoformat(view.opened_ts_utc)
            except ValueError:
                opened_at = datetime.fromtimestamp(self._clock.now(), UTC)
            out.append(
                Position(
                    ticket_id=view.ticket_id,
                    mint=key,
                    correlation_id=view.correlation_id,
                    price_entry=view.price_entry,
                    price_peak=view.price_peak,
                    cost_basis_lamports=view.cost_basis_lamports,
                    token_units=view.token_units,
                    opened_at=opened_at,
                    price_mark=None,
                    last_mtm_lamports=view.last_mtm_lamports,
                    unrealised_pnl_lamports=int(view.last_mtm_lamports)
                    - int(view.cost_basis_lamports),
                    unrealised_pnl_pct=None,
                    mtm_source="live",
                    mtm_frozen=view.mtm_frozen,
                )
            )
        return out

    # -- graduation, blind, marks (PAPER-005) --------------------------------

    async def close_on_graduation(
        self,
        mint: str,
        *,
        last_s: int,
        last_t: int,
        source: str | None = None,
        correlation_id: str = "desk",
    ) -> dict[str, Any] | None:
        """Force-close the open position at the last pre-graduation sell_out.

        Returns the PositionClosed row, or None when no position is open.
        Appends an Escalation(kind=graduated) and freezes the mark.
        """
        return await self._force_close(
            mint,
            reason="graduated",
            last_s=last_s,
            last_t=last_t,
            source=source,
            correlation_id=correlation_id,
        )

    async def check_blind(
        self,
        mint: str,
        *,
        source: str | None = None,
        correlation_id: str = "desk",
    ) -> dict[str, Any] | None:
        """Force-close at last_good after ``blind_max_s`` without a price.

        Returns the PositionClosed row, or None when the position is fresh,
        absent, or has no last-good value yet.
        """
        state = self._fold_state()
        pos = state.positions.get(mint)
        if pos is None or pos.token_units <= 0:
            return None
        last_ts = self._last_price_ts.get(mint)
        if last_ts is None:
            last_ts = _ledger_mark_epoch(pos)
        if last_ts is None:
            return None
        if self._clock.now() - last_ts <= float(self._limits.blind_max_s):
            return None
        last = self._last_reserves.get(mint)
        if pos.last_mtm_lamports > 0:
            last_good = int(pos.last_mtm_lamports)
        elif last is not None:
            last_good = sell_out(last[0], last[1], pos.token_units)
            last_good -= self._fees.venue_fee(last_good)
        else:
            return None
        return await self._force_close(
            mint,
            reason="blind_flatten",
            last_good_lamports=last_good,
            source=source,
            correlation_id=correlation_id,
        )

    async def mark_to_market(
        self,
        mint: str,
        *,
        source: str | None = None,
        correlation_id: str = "desk",
    ) -> dict[str, Any] | None:
        """Mark one open position to liquidation value; None when flat."""
        ledger_source = source if source is not None else self._source
        state = self._fold_state()
        pos = state.positions.get(mint)
        if pos is None or pos.token_units <= 0 or pos.mtm_frozen:
            return None
        curve = await self._read_curve(mint)
        if curve is None or curve.complete:
            return None
        gross = sell_out(curve.s_lamports, curve.t_units, pos.token_units)
        mtm = gross - self._fees.venue_fee(gross)
        cash = int(state.cash_lamports)
        # Book value: this mint at the fresh mark, every other open position at
        # its last ledger mark (the same sum the fold uses for equity).
        others = [p for key, p in state.positions.items() if key != mint and p.token_units > 0]
        book_mtm = mtm + sum(int(p.last_mtm_lamports) for p in others)
        book_basis = int(pos.cost_basis_lamports) + sum(int(p.cost_basis_lamports) for p in others)
        equity = cash + book_mtm
        unrealized = book_mtm - book_basis
        prices_json = canonical_json(
            {
                mint: {
                    "mtm_lamports": mtm,
                    "spot": str(spot(curve.s_lamports, curve.t_units)),
                    "source": "curve",
                }
            }
        )
        row = self._store.append(
            ts_utc=self._now_ts(),
            source=ledger_source,
            correlation_id=correlation_id,
            idempotency_key=f"mtm|{mint}|{self._now_ts()}",
            type="MarkToMarket",
            payload={
                "source": ledger_source,
                "ts_source": self._now_ts(),
                "cash_lamports": cash,
                "equity_lamports": equity,
                "unrealized_lamports": unrealized,
                "prices_json": prices_json,
            },
        )
        self._last_price_ts[mint] = self._clock.now()
        self._last_reserves[mint] = (curve.s_lamports, curve.t_units)
        return row

    def frozen_mark(self, mint: str) -> int | None:
        """Frozen liquidation value after a graduated/blind_flatten close."""
        return self._frozen_marks.get(mint)

    async def close_position(
        self,
        *,
        mint: str,
        ticket_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """Close the open position in ``mint`` at its liquidation value (RISK-004).

        Reuses the forced-close path: one sell ``FillRecorded`` and one
        ``PositionClosed`` carrying ``reason``. The value comes from the live
        curve; with no usable curve it falls back to the last ledger mark, then
        the last-good reserves. Returns ``status="closed"`` after writing, or
        ``status="no_position"`` (nothing written) when no position is open.
        ``status="no_mark"`` (nothing written) means the position is open but no
        value can be derived; the caller must retry or escalate. Never raises for
        a missing position; only an unsupported ``reason`` raises ``ValueError``.
        """
        if reason not in SYSTEM_EXIT_REASONS:
            raise ValueError(f"unsupported close reason: {reason}")
        state = self._fold_state()
        pos = state.positions.get(mint)
        if pos is None or pos.token_units <= 0:
            return {"status": "no_position", "mint": mint}
        value = await self._liquidation_value(mint, pos)
        if value is None:
            return {"status": "no_mark", "mint": mint}
        row = await self._force_close(
            mint,
            reason=reason,  # type: ignore[arg-type]
            last_good_lamports=value,
            source=None,
            correlation_id=ticket_id,
            ticket_id=ticket_id,
        )
        if row is None:
            return {"status": "no_position", "mint": mint}
        return {
            "status": "closed",
            "mint": mint,
            "reason": reason,
            "proceeds_lamports": value,
            "realized_pnl_lamports": value - int(pos.cost_basis_lamports),
            "seq": int(row["seq"]),
        }

    async def _liquidation_value(self, mint: str, pos: PositionView) -> int | None:
        """Net liquidation value of ``pos`` now; None when no value is derivable."""
        curve = await self._read_curve(mint)
        if curve is not None and not curve.complete:
            gross = sell_out(curve.s_lamports, curve.t_units, pos.token_units)
            return gross - self._fees.venue_fee(gross)
        if pos.last_mtm_lamports > 0:
            return int(pos.last_mtm_lamports)
        last = self._last_reserves.get(mint)
        if last is not None:
            gross = sell_out(last[0], last[1], pos.token_units)
            return gross - self._fees.venue_fee(gross)
        return None

    async def _force_close(
        self,
        mint: str,
        *,
        reason: Literal["graduated", "blind_flatten", "kill_flatten", "rug_alert"],
        last_s: int = 0,
        last_t: int = 0,
        last_good_lamports: int = 0,
        source: str | None,
        correlation_id: str,
        ticket_id: str = "",
    ) -> dict[str, Any] | None:
        ledger_source = source if source is not None else self._source
        state = self._fold_state()
        pos = state.positions.get(mint)
        if pos is None or pos.token_units <= 0:
            return None
        venue_fee = 0
        if reason == "graduated":
            gross = sell_out(last_s, last_t, pos.token_units)
            venue_fee = self._fees.venue_fee(gross)
            proceeds = gross - venue_fee
        else:
            proceeds = last_good_lamports
        realized = proceeds - int(pos.cost_basis_lamports)
        basis = int(pos.cost_basis_lamports)
        pnl_pct = Decimal(realized) / Decimal(basis) if basis else Decimal("0")
        try:
            hold_s = int(self._clock.now() - parse_ts_utc(pos.opened_ts_utc))
        except ValueError:
            hold_s = 0
        venue_tx_ref = f"dry_run:{self._ids.ulid()}"
        order_id = self._ids.ulid()
        price_exit = str(Decimal(proceeds) / Decimal(pos.token_units)) if pos.token_units else "0"
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
                    "decision_id": "",
                    "side": "sell",
                    "mint": mint,
                    "filled_lamports": proceeds,
                    "filled_units": pos.token_units,
                    "filled_fraction": "1",
                    "price_avg": price_exit,
                    "venue_fee_lamports": venue_fee,
                    "network_cost_lamports": 0,
                    "cash_delta_lamports": proceeds,
                    "venue_tx_ref": venue_tx_ref,
                    "route": "curve",
                },
            },
            {
                "ts_utc": self._now_ts(),
                "source": ledger_source,
                "correlation_id": correlation_id,
                "idempotency_key": f"close|{reason}|{mint}|{self._now_ts()}",
                "type": "PositionClosed",
                "payload": {
                    "source": ledger_source,
                    "mint": mint,
                    "price_exit": str(Decimal(proceeds) / Decimal(pos.token_units))
                    if pos.token_units
                    else "0",
                    "proceeds_lamports": proceeds,
                    "realized_pnl_lamports": realized,
                    "reason": reason,
                    "pnl_pct": str(pnl_pct),
                    "hold_seconds": max(hold_s, 0),
                    "venue_tx_ref": venue_tx_ref,
                },
            },
            {
                "ts_utc": self._now_ts(),
                "source": ledger_source,
                "correlation_id": correlation_id,
                "idempotency_key": f"escalation|{reason}|{mint}|{self._now_ts()}",
                "type": "Escalation",
                "payload": {
                    "source": ledger_source,
                    "kind": reason,
                    "seat": "bot-06-exit",
                    "detail": f"{reason} mint={mint} mtm_lamports={proceeds} frozen=true"
                    + (f" ticket={ticket_id}" if ticket_id else ""),
                },
            },
        ]
        stored = self._store.append_batch(rows)
        self._frozen_marks[mint] = proceeds
        self._last_price_ts.pop(mint, None)
        return stored[1]


def _at_iso(at: Any) -> str:
    if isinstance(at, datetime):
        return at.isoformat()
    return str(at)


def _ledger_mark_epoch(pos: PositionView) -> float | None:
    """Epoch of the last ledger mark for an open position; None when unmarked."""
    if not pos.last_mtm_ts_utc:
        return None
    try:
        return parse_ts_utc(pos.last_mtm_ts_utc)
    except ValueError:
        return None
