"""Curve quotes and pure-math fill previews."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from pumpgrok.core.adapter import Quote, Side, SimulationResult
from pumpgrok.core.errors import OrderRejectedError
from pumpgrok.execution.curve_math import buy_out, impact_buy, impact_sell, sell_out, spot


if TYPE_CHECKING:
    from pumpgrok.core.ids import Clock, IdFactory
    from pumpgrok.execution.fees import FeeModel
    from pumpgrok.execution.paper_adapter.models import CurveSnapshot


class _QuoteMixin:
    if TYPE_CHECKING:
        _clock: Clock
        _fees: FeeModel
        _ids: IdFactory

        async def _read_curve(self, mint: str) -> CurveSnapshot | None: ...

        def _fill_cap(self, s_lamports: int) -> int: ...

        def _floor(self, size_lamports: int) -> int: ...

        @staticmethod
        def _sell_preview_units(
            size_lamports: int | None, token_units: int | None, curve: CurveSnapshot
        ) -> int: ...

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
