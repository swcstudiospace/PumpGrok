"""Graduation, blind-flatten, marks, and forced closes."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal

from pumpgrok.core.idempotency import canonical_json
from pumpgrok.execution.curve_math import sell_out, spot
from pumpgrok.execution.paper_adapter.models import CurveSnapshot, _ledger_mark_epoch
from pumpgrok.ledger.reducer import PositionView
from pumpgrok.ledger.store import LedgerInconsistent
from pumpgrok.replay.clock import format_ts_utc, parse_ts_utc
from pumpgrok.risk.engine import SYSTEM_EXIT_REASONS


class _MarksMixin:
    if TYPE_CHECKING:
        from pumpgrok.core.ids import Clock, IdFactory
        from pumpgrok.execution.fees import FeeModel
        from pumpgrok.ledger.store import LedgerStore
        from pumpgrok.risk.limits import EngineLimits

        _clock: Clock
        _fees: FeeModel
        _frozen_marks: dict[str, int]
        _ids: IdFactory
        _last_price_ts: dict[str, float]
        _last_reserves: dict[str, tuple[int, int]]
        _limits: EngineLimits
        _source: Literal["paper", "replay", "manual"]
        _store: LedgerStore

        def _fold_state(self) -> Any: ...

        def _now_ts(self) -> str: ...

        async def _read_curve(self, mint: str) -> CurveSnapshot | None: ...

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
        Appends an Escalation(kind=graduated) and freezes the mark. The close
        books the venue fee and network cost, as a normal sell does.
        """
        state = self._fold_state()
        pos = state.positions.get(mint)
        if pos is None or pos.token_units <= 0:
            return None
        return await self._force_close(
            mint,
            reason="graduated",
            valued=self._curve_exit(last_s, last_t, pos.token_units),
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
        valued = self._last_good_value(mint, pos)
        if valued is None:
            return None
        return await self._force_close(
            mint,
            reason="blind_flatten",
            valued=valued,
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
        venue = self._fees.venue_fee(gross)
        mtm = gross - venue
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
                    "venue_fee_lamports": venue,
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

    async def mark_open_positions(
        self,
        *,
        source: str | None = None,
        correlation_id: str = "desk",
    ) -> dict[str, Any] | None:
        """Mark every open position in one ``MarkToMarket`` row for this instant.

        All prices are read before anything is written, so the row carries the combined
        equity and the reducer's peak never sees a mix of new and old prices. Each mint's
        mark keeps the recorded time of the snapshot it was priced from, not the current
        time, so a silent mint shows its true age. A position with no usable curve keeps
        its last ledger mark. Returns the row, or None when nothing is open or this exact
        state was already marked at this instant.
        """
        ledger_source = source if source is not None else self._source
        state = self._fold_state()
        held = {m: p for m, p in state.positions.items() if p.token_units > 0 and not p.mtm_frozen}
        if not held:
            return None
        now = self._clock.now()
        marks: dict[str, dict[str, Any]] = {}
        values: dict[str, int] = {}
        for mint, pos in held.items():
            curve = await self._read_curve(mint)
            if curve is None or curve.complete:
                values[mint] = int(pos.last_mtm_lamports)
                continue
            recorded = curve.ts if curve.ts is not None else now
            gross = sell_out(curve.s_lamports, curve.t_units, pos.token_units)
            venue = self._fees.venue_fee(gross)
            values[mint] = gross - venue
            marks[mint] = {
                "mtm_lamports": gross - venue,
                "venue_fee_lamports": venue,
                "spot": str(spot(curve.s_lamports, curve.t_units)),
                "source": "curve",
                "ts_utc": format_ts_utc(recorded),
            }
            self._last_reserves[mint] = (curve.s_lamports, curve.t_units)
            self._last_price_ts[mint] = recorded
        if not marks:
            return None
        cash = int(state.cash_lamports)
        equity = cash + sum(values.values())
        basis = sum(int(p.cost_basis_lamports) for p in held.values())
        unrealized = sum(values.values()) - basis
        prices_json = canonical_json(marks)
        basis_by_mint = {m: int(p.cost_basis_lamports) for m, p in held.items()}
        key = canonical_json({"at": self._now_ts(), "prices": marks, "basis": basis_by_mint})
        if self._store.by_key(f"mtm|{key}") is not None:
            return None
        return self._store.append(
            ts_utc=self._now_ts(),
            source=ledger_source,
            correlation_id=correlation_id,
            idempotency_key=f"mtm|{key}",
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
        """Close the open position in ``mint`` at its net liquidation value (RISK-004).

        Reuses the forced-close path: one sell ``FillRecorded`` and one
        ``PositionClosed`` carrying ``reason``. The value comes from the live
        curve; with no usable curve it falls back to the last ledger mark, then
        the last-good reserves. The sell books the venue fee and network cost, so
        cash moves by the value and reported fees agree. Returns
        ``status="closed"`` after writing. ``status="no_position"`` means no
        position is open; ``status="no_mark"`` means one is open but no value can
        be derived; ``status="ledger_inconsistent"`` means the ledger failed
        verification. The last three write nothing and never raise. Only an
        unsupported ``reason`` raises ``ValueError``.
        """
        if reason not in SYSTEM_EXIT_REASONS:
            raise ValueError(f"unsupported close reason: {reason}")
        try:
            self._store.verify()
        except LedgerInconsistent:
            return {"status": "ledger_inconsistent", "mint": mint}
        curve = await self._read_curve(mint)
        state = self._fold_state()
        pos = state.positions.get(mint)
        if pos is None or pos.token_units <= 0:
            return {"status": "no_position", "mint": mint}
        valued = self._live_value(mint, pos, curve)
        if valued is None:
            return {"status": "no_mark", "mint": mint}
        proceeds = valued[0]
        row = await self._force_close(
            mint,
            reason=reason,  # type: ignore[arg-type]
            valued=valued,
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
            "proceeds_lamports": proceeds,
            "realized_pnl_lamports": proceeds - int(pos.cost_basis_lamports),
            "seq": int(row["seq"]),
        }

    def _curve_exit(self, s_lamports: int, t_units: int, units: int) -> tuple[int, int, int]:
        """``(proceeds, venue_fee, network_cost)`` for selling ``units`` on this curve.

        Same arithmetic as a normal sell: proceeds are gross less venue fee less
        network cost, so cash moves by the proceeds and fees are reported.
        """
        gross = sell_out(s_lamports, t_units, units)
        venue = self._fees.venue_fee(gross)
        network = self._fees.network_cost()
        return gross - venue - network, venue, network

    def _last_good_value(self, mint: str, pos: PositionView) -> tuple[int, int, int] | None:
        """Last ledger mark, else the last-good reserves; never reads a live price.

        A ledger mark is already net of the venue fee, so the close takes only the
        network cost off it and books the venue fee stored with that mark. Marks
        written before the venue key existed report a venue fee of 0 (disclosed);
        their cash is unaffected. The reserves path reports both fees.
        """
        if pos.last_mtm_lamports > 0:
            network = self._fees.network_cost()
            return (
                int(pos.last_mtm_lamports) - network,
                int(pos.last_mtm_venue_fee_lamports),
                network,
            )
        last = self._last_reserves.get(mint)
        if last is not None:
            return self._curve_exit(last[0], last[1], pos.token_units)
        return None

    def _live_value(
        self, mint: str, pos: PositionView, curve: CurveSnapshot | None
    ) -> tuple[int, int, int] | None:
        """Value of a full exit: the live curve when usable, else the last-good value."""
        if curve is not None and not curve.complete:
            return self._curve_exit(curve.s_lamports, curve.t_units, pos.token_units)
        return self._last_good_value(mint, pos)

    async def _force_close(
        self,
        mint: str,
        *,
        reason: Literal["graduated", "blind_flatten", "kill_flatten", "rug_alert"],
        valued: tuple[int, int, int],
        source: str | None,
        correlation_id: str,
        ticket_id: str = "",
    ) -> dict[str, Any] | None:
        ledger_source = source if source is not None else self._source
        state = self._fold_state()
        pos = state.positions.get(mint)
        if pos is None or pos.token_units <= 0:
            return None
        proceeds, venue_fee, network_cost = valued
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
                    "network_cost_lamports": network_cost,
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
