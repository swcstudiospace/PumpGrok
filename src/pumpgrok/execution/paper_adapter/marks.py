"""Graduation, blind-flatten, marks, and forced closes."""

from __future__ import annotations

import math
from collections.abc import Mapping, Set
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from pumpgrok.core.idempotency import canonical_json
from pumpgrok.execution.curve_math import sell_out, spot
from pumpgrok.execution.deposits import open_deposits
from pumpgrok.execution.entry_hook import bound_replay_source
from pumpgrok.execution.paper_adapter.models import CurveSnapshot, _ledger_mark_epoch
from pumpgrok.ledger.reducer import PositionView, position_value_lamports
from pumpgrok.ledger.store import LedgerInconsistent
from pumpgrok.replay.clock import format_ts_utc, parse_ts_utc
from pumpgrok.risk.engine import SYSTEM_EXIT_REASONS
from pumpgrok.tools.onchain import curve_layout
from pumpgrok.tools.onchain.curve_layout import CurveProvenance

if TYPE_CHECKING:
    from pumpgrok.core.ids import Clock, IdFactory
    from pumpgrok.execution.entry_hook import EntryPolicy
    from pumpgrok.execution.fees import FeeModel
    from pumpgrok.execution.paper_adapter.models import PriceSource
    from pumpgrok.ledger.store import LedgerStore
    from pumpgrok.risk.limits import EngineLimits


class _ExitValue(NamedTuple):
    """A full exit's value: proceeds net of fees, and the ATA deposit credited beside them.

    ``proceeds`` is the close's reported proceeds. ``refund`` is the deposit the close
    returns to cash on top of proceeds; it is zero when the valuation already holds it.
    """

    proceeds: int
    venue_fee: int
    network_cost: int
    refund: int


def _realized_lamports(valued: _ExitValue, pos: PositionView) -> int:
    """Realized P&L of a full exit: the cash it credits, less the full cost basis.

    The deposit sits in both the cost basis and the credit, so it nets to zero.
    """
    return valued.proceeds + valued.refund - int(pos.cost_basis_lamports)


class _MarksMixin:
    if TYPE_CHECKING:
        _clock: Clock
        _entry_policy: EntryPolicy | None
        _fees: FeeModel
        _frozen_marks: dict[str, int]
        _ids: IdFactory
        _last_price_ts: dict[str, float]
        _price: PriceSource | None
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
            valued=self._curve_exit(mint, last_s, last_t, pos.token_units),
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
        mtm = gross - venue + self._open_deposits().get(mint, 0)
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
        snapshots: Mapping[str, CurveSnapshot] | None = None,
        zero_mints: Set[str] | None = None,
    ) -> dict[str, Any] | None:
        """Mark every open position in one ``MarkToMarket`` row for this instant.

        By default, curves are read from the adapter's price source. When either
        ``snapshots`` or ``zero_mints`` is supplied, those inputs are authoritative:
        omitted positions retain their last value and no price source is read.
        Supplied snapshots must match an open mint and pass the current trust gate.
        Nonempty zero marks are rejected until durable last-good exits are supported.
        All marks for this instant are written in one row.
        """
        if zero_mints:
            raise ValueError("timeout-zero marks require durable last-good exit support")
        ledger_source = source if source is not None else self._source
        state = self._fold_state()
        held = {m: p for m, p in state.positions.items() if p.token_units > 0 and not p.mtm_frozen}
        now = self._clock.now()
        supplied = snapshots is not None or zero_mints is not None
        if supplied:
            supplied_snapshots = snapshots if snapshots is not None else {}
            self._validate_supplied_marks(held, supplied_snapshots, now)
        if not held:
            return None
        if supplied:
            marks, values = self._price_supplied(
                held, supplied_snapshots, now, self._open_deposits()
            )
        else:
            marks, values = await self._price_held(held, now, self._open_deposits())
        if not marks:
            return None
        row = self._append_mark_row(
            state,
            held,
            marks=marks,
            values=values,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
        )
        if supplied and row is not None:
            for mint, curve in supplied_snapshots.items():
                self._last_reserves[mint] = (curve.s_lamports, curve.t_units)
                self._last_price_ts[mint] = curve.ts if curve.ts is not None else now
        return row

    def _validate_supplied_marks(
        self,
        held: dict[str, PositionView],
        snapshots: Mapping[str, CurveSnapshot],
        now: float,
    ) -> None:
        """Reject the whole batch before pricing, writing or changing caches."""
        if set(snapshots) - held.keys():
            raise ValueError("mark input contains a mint without an open position")
        for mint, curve in snapshots.items():
            # Supplied snapshots carry no source identity: they are never replay.
            if not self._admitted_curve(mint, curve, self._provenance(None, curve)):
                raise ValueError(f"untrusted or invalid curve snapshot for {mint}")
            if not self._admitted_timestamp(mint, held[mint], curve, now):
                raise ValueError(f"invalid curve snapshot timestamp for {mint}")

    def _admitted_timestamp(
        self, mint: str, pos: PositionView, curve: CurveSnapshot, now: float
    ) -> bool:
        recorded = curve.ts if curve.ts is not None else now
        ledger_time = _ledger_mark_epoch(pos)
        cached_time = self._last_price_ts.get(mint)
        return (
            math.isfinite(recorded)
            and recorded <= now
            and (ledger_time is None or recorded >= ledger_time)
            and (cached_time is None or recorded >= cached_time)
        )

    def _provenance(self, read_from: object | None, curve: CurveSnapshot) -> CurveProvenance:
        """Provenance of one mark snapshot.

        VERIFIED_REPLAY only when the read came from the curve source bound by
        ``verify_replay`` (identity check). LIVE_RPC for an rpc label. Anything
        else, including a fixture label from any other source, is UNKNOWN.
        """
        if read_from is not None and read_from is bound_replay_source(self._entry_policy):
            return CurveProvenance.VERIFIED_REPLAY
        if curve.source == "rpc":
            return CurveProvenance.LIVE_RPC
        return CurveProvenance.UNKNOWN

    @staticmethod
    def _admitted_curve(mint: str, curve: CurveSnapshot, provenance: CurveProvenance) -> bool:
        return (
            curve.mint == mint
            and curve.source in {"fixture", "rpc"}
            and not curve.complete
            and curve.s_lamports > 0
            and curve.t_units > 0
            and curve_layout.rpc_curve_price_allowed(
                curve_source=curve.source, provenance=provenance
            )
        )

    def _open_deposits(self) -> dict[str, int]:
        """ATA deposit held by each mint's open account, from the deposit sidecar."""
        return open_deposits(self._store)

    def _price_supplied(
        self,
        held: dict[str, PositionView],
        snapshots: Mapping[str, CurveSnapshot],
        now: float,
        deposits: Mapping[str, int],
    ) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
        """Value validated supplied observations without reading or changing caches."""
        marks: dict[str, dict[str, Any]] = {}
        values = {mint: position_value_lamports(pos) for mint, pos in held.items()}
        for mint, curve in snapshots.items():
            gross = sell_out(curve.s_lamports, curve.t_units, held[mint].token_units)
            venue = self._fees.venue_fee(gross)
            mtm = gross - venue + deposits.get(mint, 0)
            values[mint] = mtm
            marks[mint] = {
                "mtm_lamports": mtm,
                "venue_fee_lamports": venue,
                "spot": str(spot(curve.s_lamports, curve.t_units)),
                "source": "curve",
                "ts_utc": format_ts_utc(curve.ts if curve.ts is not None else now),
            }
        return marks, values

    async def _price_held(
        self,
        held: dict[str, PositionView],
        now: float,
        deposits: Mapping[str, int],
    ) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
        """Read each held mint's curve; a mint with no usable curve keeps its last mark."""
        marks: dict[str, dict[str, Any]] = {}
        values: dict[str, int] = {}
        for mint, pos in held.items():
            read_from = self._price
            curve = await self._read_curve(mint)
            if curve is None or not self._admitted_curve(
                mint, curve, self._provenance(read_from, curve)
            ):
                values[mint] = position_value_lamports(pos)
                continue
            if not self._admitted_timestamp(mint, pos, curve, now):
                values[mint] = position_value_lamports(pos)
                continue
            recorded = curve.ts if curve.ts is not None else now
            gross = sell_out(curve.s_lamports, curve.t_units, pos.token_units)
            venue = self._fees.venue_fee(gross)
            mtm = gross - venue + deposits.get(mint, 0)
            values[mint] = mtm
            marks[mint] = {
                "mtm_lamports": mtm,
                "venue_fee_lamports": venue,
                "spot": str(spot(curve.s_lamports, curve.t_units)),
                "source": "curve",
                "ts_utc": format_ts_utc(recorded),
            }
            self._last_reserves[mint] = (curve.s_lamports, curve.t_units)
            self._last_price_ts[mint] = recorded
        return marks, values

    def _append_mark_row(
        self,
        state: Any,
        held: dict[str, PositionView],
        *,
        marks: dict[str, dict[str, Any]],
        values: dict[str, int],
        ledger_source: str,
        correlation_id: str,
    ) -> dict[str, Any] | None:
        """Append one MarkToMarket row unless this exact priced state is already on the ledger."""
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
            "proceeds_lamports": valued.proceeds,
            "realized_pnl_lamports": _realized_lamports(valued, pos),
            "seq": int(row["seq"]),
        }

    def _curve_exit(self, mint: str, s_lamports: int, t_units: int, units: int) -> _ExitValue:
        """Exit value for selling ``units`` on this curve, as a normal sell books it.

        Proceeds are gross less venue fee less network cost. The open account's ATA deposit is
        not sale value: it is refunded to cash beside the proceeds.
        """
        gross = sell_out(s_lamports, t_units, units)
        venue = self._fees.venue_fee(gross)
        network = self._fees.network_cost()
        refund = self._open_deposits().get(mint, 0)
        return _ExitValue(gross - venue - network, venue, network, refund)

    def _last_good_value(self, mint: str, pos: PositionView) -> _ExitValue | None:
        """Last ledger mark, else the last-good reserves; never reads a live price.

        A ledger mark is market value and already holds the open account's ATA deposit, so
        its proceeds are the mark less the network cost: the deposit returns to cash inside
        them, once, with no separate refund. Marks written before the venue key existed
        report a venue fee of 0 (disclosed); their cash is unaffected. The reserves path
        refunds the deposit beside its proceeds instead.
        """
        if pos.last_mtm_lamports > 0:
            network = self._fees.network_cost()
            return _ExitValue(
                int(pos.last_mtm_lamports) - network,
                int(pos.last_mtm_venue_fee_lamports),
                network,
                0,
            )
        last = self._last_reserves.get(mint)
        if last is not None:
            return self._curve_exit(mint, last[0], last[1], pos.token_units)
        return None

    def _live_value(
        self, mint: str, pos: PositionView, curve: CurveSnapshot | None
    ) -> _ExitValue | None:
        """Value of a full exit: the live curve when usable, else the last-good value."""
        if curve is not None and not curve.complete:
            return self._curve_exit(mint, curve.s_lamports, curve.t_units, pos.token_units)
        return self._last_good_value(mint, pos)

    async def _force_close(
        self,
        mint: str,
        *,
        reason: Literal["graduated", "blind_flatten", "kill_flatten", "rug_alert"],
        valued: _ExitValue,
        source: str | None,
        correlation_id: str,
        ticket_id: str = "",
    ) -> dict[str, Any] | None:
        ledger_source = source if source is not None else self._source
        state = self._fold_state()
        pos = state.positions.get(mint)
        if pos is None or pos.token_units <= 0:
            return None
        proceeds = valued.proceeds
        realized = _realized_lamports(valued, pos)
        # PnL % is taken against cost basis net of the deposit, which the close refunds.
        deposit = self._open_deposits().get(mint, 0)
        pnl_pct, hold_seconds = self._close_stats(pos, realized, deposit)
        venue_tx_ref = f"dry_run:{self._ids.ulid()}"
        order_id = self._ids.ulid()
        price_exit = str(Decimal(proceeds) / Decimal(pos.token_units)) if pos.token_units else "0"
        rows = self._force_close_rows(
            mint,
            reason=reason,
            valued=valued,
            realized=realized,
            pnl_pct=pnl_pct,
            hold_s=hold_seconds,
            order_id=order_id,
            venue_tx_ref=venue_tx_ref,
            units=pos.token_units,
            price_exit=price_exit,
            ticket_id=ticket_id,
            ledger_source=ledger_source,
            correlation_id=correlation_id,
        )
        stored = self._store.append_batch(rows)
        self._frozen_marks[mint] = proceeds
        self._last_price_ts.pop(mint, None)
        return stored[1]

    def _force_close_rows(
        self,
        mint: str,
        *,
        reason: str,
        valued: _ExitValue,
        realized: int,
        pnl_pct: Decimal,
        hold_s: int,
        order_id: str,
        venue_tx_ref: str,
        units: int,
        price_exit: str,
        ticket_id: str,
        ledger_source: str,
        correlation_id: str,
    ) -> list[dict[str, Any]]:
        """Fill, close and escalation rows of one forced close, in ledger order."""
        return [
            self._force_close_fill_row(
                mint,
                order_id=order_id,
                venue_tx_ref=venue_tx_ref,
                proceeds=valued.proceeds,
                venue_fee=valued.venue_fee,
                network_cost=valued.network_cost,
                refund_lamports=valued.refund,
                units=units,
                price_exit=price_exit,
                ledger_source=ledger_source,
                correlation_id=correlation_id,
            ),
            self._force_close_position_row(
                mint,
                reason=reason,
                proceeds=valued.proceeds,
                realized=realized,
                pnl_pct=pnl_pct,
                hold_s=hold_s,
                venue_tx_ref=venue_tx_ref,
                price_exit=price_exit,
                ledger_source=ledger_source,
                correlation_id=correlation_id,
            ),
            self._force_close_escalation_row(
                mint,
                reason=reason,
                proceeds=valued.proceeds,
                ticket_id=ticket_id,
                ledger_source=ledger_source,
                correlation_id=correlation_id,
            ),
        ]

    def _close_stats(self, pos: PositionView, realized: int, deposit: int) -> tuple[Decimal, int]:
        """PnL fraction against basis net of the refunded deposit; hold seconds floored at zero."""
        basis = int(pos.cost_basis_lamports) - deposit
        pnl_pct = Decimal(realized) / Decimal(basis) if basis else Decimal("0")
        try:
            hold_s = int(self._clock.now() - parse_ts_utc(pos.opened_ts_utc))
        except ValueError:
            hold_s = 0
        return pnl_pct, max(hold_s, 0)

    def _force_close_fill_row(
        self,
        mint: str,
        *,
        order_id: str,
        venue_tx_ref: str,
        proceeds: int,
        venue_fee: int,
        network_cost: int,
        refund_lamports: int,
        units: int,
        price_exit: str,
        ledger_source: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        return {
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
                "filled_units": units,
                "filled_fraction": "1",
                "price_avg": price_exit,
                "venue_fee_lamports": venue_fee,
                "network_cost_lamports": network_cost,
                "cash_delta_lamports": proceeds + refund_lamports,
                "venue_tx_ref": venue_tx_ref,
                "route": "curve",
            },
        }

    def _force_close_position_row(
        self,
        mint: str,
        *,
        reason: str,
        proceeds: int,
        realized: int,
        pnl_pct: Decimal,
        hold_s: int,
        venue_tx_ref: str,
        price_exit: str,
        ledger_source: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        return {
            "ts_utc": self._now_ts(),
            "source": ledger_source,
            "correlation_id": correlation_id,
            "idempotency_key": f"close|{reason}|{mint}|{self._now_ts()}",
            "type": "PositionClosed",
            "payload": {
                "source": ledger_source,
                "mint": mint,
                "price_exit": price_exit,
                "proceeds_lamports": proceeds,
                "realized_pnl_lamports": realized,
                "reason": reason,
                "pnl_pct": str(pnl_pct),
                "hold_seconds": hold_s,
                "venue_tx_ref": venue_tx_ref,
            },
        }

    def _force_close_escalation_row(
        self,
        mint: str,
        *,
        reason: str,
        proceeds: int,
        ticket_id: str,
        ledger_source: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        return {
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
        }
