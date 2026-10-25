"""PaperAdapter shell: construction, ledger reads, cancel, and positions."""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pumpgrok.core.adapter import ExecutionAdapter, ExecutionMode, OrderRequest, Position
from pumpgrok.core.ids import Clock, IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.fees import FeeModel
from pumpgrok.execution.latency import P_DROP
from pumpgrok.execution.paper_adapter.batch import _BatchMixin
from pumpgrok.execution.paper_adapter.buy import _BuyMixin
from pumpgrok.execution.paper_adapter.confirm import _ConfirmMixin
from pumpgrok.execution.paper_adapter.marks import _MarksMixin
from pumpgrok.execution.paper_adapter.models import CurveSnapshot, PriceSource, _InflightOrders
from pumpgrok.execution.paper_adapter.quote import _QuoteMixin
from pumpgrok.execution.paper_adapter.sell import _SellMixin
from pumpgrok.ledger.reducer import initial_state, reduce
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import format_ts_utc
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.killswitch import InflightBarrier
from pumpgrok.risk.limits import EngineLimits


class PaperAdapter(
    _BuyMixin,
    _SellMixin,
    _ConfirmMixin,
    _QuoteMixin,
    _BatchMixin,
    _MarksMixin,
    ExecutionAdapter,
):
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
        self._p_drop = p_drop
        self._inflight = _InflightOrders()
        self._cancelled: set[str] = set()
        self._last_price_ts: dict[str, float] = {}
        self._last_reserves: dict[str, tuple[int, int]] = {}
        self._frozen_marks: dict[str, int] = {}
        self._active_places: set[str] = set()
        # Per-call owner token -> the order that call registered in the barrier.
        self._owned_order: dict[object, str] = {}

    @property
    def inflight_barrier(self) -> InflightBarrier:
        """The barrier the kill-switch flatten waits on; orders are in it while in flight."""
        return self._inflight.barrier

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
