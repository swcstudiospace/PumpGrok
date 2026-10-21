"""Pure ledger fold: reduce(state, event) -> state (paper-engine.md 3.4, R26).

Total: unknown event types are recorded in ``state.unknown_events`` and
otherwise ignored, so a newer process can read an older ledger and vice
versa. No I/O, no clock, no randomness; the same event list always folds to
the same state.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pumpgrok.ledger.events import MoneyInt, PriceDecimal


class PositionView(BaseModel):
    """One open position derived from fills and marks (paper-engine.md 2.1)."""

    model_config = ConfigDict(frozen=True)

    mint: str
    symbol: str = ""
    creator: str = ""
    ticket_id: str = ""
    correlation_id: str = ""
    price_entry: PriceDecimal = Decimal("0")
    price_peak: PriceDecimal = Decimal("0")
    token_units: MoneyInt = 0
    cost_basis_lamports: MoneyInt = 0
    fees_lamports: MoneyInt = 0
    opened_ts_utc: str = ""
    last_mtm_lamports: MoneyInt = 0
    last_mtm_ts_utc: str = ""
    mtm_source: str = ""
    mtm_frozen: bool = False


class HaltView(BaseModel):
    model_config = ConfigDict(frozen=True)

    active: bool = False
    reason: str = ""
    since: str = ""


class KillSwitchView(BaseModel):
    model_config = ConfigDict(frozen=True)

    active: bool = False
    source: str = ""
    since: str = ""
    flatten_requested: bool = False


class BreakerView(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: str = "closed"
    since: str = ""
    until: str = ""


class ApprovalView(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    consumed: bool = False


class CountersView(BaseModel):
    model_config = ConfigDict(frozen=True)

    trades_today: MoneyInt = 0
    rejected_today: dict[str, int] = Field(default_factory=dict)
    fees_today_lamports: MoneyInt = 0
    realized_today_lamports: int = 0


class LedgerState(BaseModel):
    """Folded ledger state (paper-engine.md 3.4)."""

    model_config = ConfigDict(frozen=True)

    seq: int = 0
    source: str = "paper"
    day_utc: str = ""
    day_start_equity_lamports: MoneyInt = 0
    peak_equity_lamports: MoneyInt = 0
    cash_lamports: int = 0
    positions: dict[str, PositionView] = Field(default_factory=dict)
    halt: HaltView = Field(default_factory=HaltView)
    kill_switch: KillSwitchView = Field(default_factory=KillSwitchView)
    breakers: dict[str, BreakerView] = Field(default_factory=dict)
    approvals: dict[str, ApprovalView] = Field(default_factory=dict)
    counters: CountersView = Field(default_factory=CountersView)
    last_mtm_ts_utc: str = ""
    unknown_events: list[str] = Field(default_factory=list)
    meta: dict[str, str] = Field(default_factory=dict)


def initial_state(
    *,
    source: str,
    initial_equity_lamports: int,
    day_utc: str,
) -> LedgerState:
    """Genesis state: cash, day-start and peak all equal initial equity."""
    return LedgerState(
        seq=0,
        source=source,
        day_utc=day_utc,
        day_start_equity_lamports=initial_equity_lamports,
        peak_equity_lamports=initial_equity_lamports,
        cash_lamports=initial_equity_lamports,
    )


def dump_state(state: LedgerState) -> dict[str, Any]:
    """JSON-safe snapshot body (Decimals as strings)."""
    return state.model_dump(mode="json")


def load_state(body: Mapping[str, Any]) -> LedgerState:
    """Restore a snapshotted state; tolerate writer-added ``meta`` keys."""
    return LedgerState.model_validate(dict(body))


def _track_peak(state: LedgerState) -> LedgerState:
    # Same sum as views.equity_lamports (kept inline to avoid a views import cycle).
    equity = int(state.cash_lamports) + sum(
        pos.last_mtm_lamports for pos in state.positions.values() if pos.token_units > 0
    )
    if equity > state.peak_equity_lamports:
        return state.model_copy(update={"peak_equity_lamports": equity})
    return state


def reduce(state: LedgerState, event: Mapping[str, Any]) -> LedgerState:
    """Fold one stored row (``read()`` shape) into a new state."""
    type = str(event.get("type", ""))
    payload = event.get("payload")
    row: dict[str, Any] = dict(payload) if isinstance(payload, Mapping) else {}
    seq = int(event.get("seq", 0))
    ts_utc = str(event.get("ts_utc", ""))
    correlation_id = str(event.get("correlation_id", ""))
    handler = _HANDLERS.get(type)
    if handler is None:
        return state.model_copy(
            update={
                "seq": seq,
                "unknown_events": [*state.unknown_events, f"{seq}:{type}"],
            }
        )
    updated = handler(state, row, ts_utc, correlation_id)
    return updated.model_copy(update={"seq": seq})


def _on_position_opened(
    state: LedgerState, row: dict[str, Any], ts_utc: str, correlation_id: str
) -> LedgerState:
    mint = str(row.get("mint", ""))
    if not mint:
        return state
    positions = dict(state.positions)
    positions[mint] = PositionView(
        mint=mint,
        symbol=str(row.get("symbol", "")),
        creator=str(row.get("creator", "")),
        ticket_id=str(row.get("ticket_id", "")),
        correlation_id=correlation_id,
        price_entry=row.get("price_entry", "0"),
        price_peak=row.get("price_entry", "0"),
        token_units=int(row.get("token_units", 0)),
        cost_basis_lamports=int(row.get("cost_basis_lamports", 0)),
        opened_ts_utc=str(row.get("opened_ts_utc", ts_utc)),
    )
    return _track_peak(state.model_copy(update={"positions": positions}))


def _on_position_closed(
    state: LedgerState, row: dict[str, Any], ts_utc: str, _correlation_id: str
) -> LedgerState:
    mint = str(row.get("mint", ""))
    positions = dict(state.positions)
    positions.pop(mint, None)
    counters = state.counters.model_copy(
        update={
            "realized_today_lamports": (
                state.counters.realized_today_lamports + int(row.get("realized_pnl_lamports", 0))
            )
        }
    )
    del ts_utc
    return _track_peak(state.model_copy(update={"positions": positions, "counters": counters}))


def _on_fill(
    state: LedgerState, row: dict[str, Any], _ts_utc: str, _correlation_id: str
) -> LedgerState:
    cash_delta = int(row.get("cash_delta_lamports", 0))
    fee = int(row.get("venue_fee_lamports", 0)) + int(row.get("network_cost_lamports", 0))
    counters = state.counters.model_copy(
        update={
            "fees_today_lamports": state.counters.fees_today_lamports + fee,
        }
    )
    positions = dict(state.positions)
    mint = str(row.get("mint", ""))
    side = str(row.get("side", ""))
    if side == "buy":
        counters = counters.model_copy(update={"trades_today": state.counters.trades_today + 1})
    pos = positions.get(mint)
    if pos is not None:
        if side == "buy":
            positions[mint] = pos.model_copy(
                update={
                    "token_units": pos.token_units + int(row.get("filled_units", 0)),
                    "cost_basis_lamports": pos.cost_basis_lamports - min(cash_delta, 0),
                    "fees_lamports": pos.fees_lamports + fee,
                }
            )
        else:
            filled = int(row.get("filled_units", 0))
            if pos.token_units > 0 and filled > 0:
                reduction = pos.cost_basis_lamports * filled // pos.token_units
                positions[mint] = pos.model_copy(
                    update={
                        "token_units": pos.token_units - filled,
                        "cost_basis_lamports": pos.cost_basis_lamports - reduction,
                    }
                )
    return _track_peak(
        state.model_copy(
            update={
                "cash_lamports": state.cash_lamports + cash_delta,
                "counters": counters,
                "positions": positions,
            }
        )
    )


def _on_rejected(
    state: LedgerState, row: dict[str, Any], _ts_utc: str, _correlation_id: str
) -> LedgerState:
    reason = str(row.get("reason", "unknown"))
    rejected = dict(state.counters.rejected_today)
    rejected[reason] = rejected.get(reason, 0) + 1
    counters = state.counters.model_copy(
        update={
            "rejected_today": rejected,
            "fees_today_lamports": (
                state.counters.fees_today_lamports + int(row.get("fees_lamports", 0))
            ),
        }
    )
    return state.model_copy(
        update={
            "cash_lamports": state.cash_lamports - int(row.get("fees_lamports", 0)),
            "counters": counters,
        }
    )


def _on_mtm(
    state: LedgerState, row: dict[str, Any], ts_utc: str, _correlation_id: str
) -> LedgerState:
    positions = dict(state.positions)
    try:
        prices = json.loads(str(row.get("prices_json", "") or "{}"))
    except (ValueError, TypeError):
        prices = {}
    if isinstance(prices, dict):
        for mint, mark in prices.items():
            if not isinstance(mark, dict):
                continue
            pos = positions.get(str(mint))
            if pos is None or pos.mtm_frozen:
                continue
            mtm = int(mark.get("mtm_lamports", pos.last_mtm_lamports))
            spot = str(mark.get("spot", "0"))
            try:
                peak = max(Decimal(pos.price_peak), Decimal(spot))
            except Exception:
                peak = pos.price_peak
            positions[str(mint)] = pos.model_copy(
                update={
                    "last_mtm_lamports": mtm,
                    "last_mtm_ts_utc": ts_utc,
                    "mtm_source": str(mark.get("source", "curve")),
                    "price_peak": peak,
                }
            )
    return _track_peak(state.model_copy(update={"positions": positions, "last_mtm_ts_utc": ts_utc}))


def _on_halt_set(
    state: LedgerState, row: dict[str, Any], ts_utc: str, _correlation_id: str
) -> LedgerState:
    return state.model_copy(
        update={"halt": HaltView(active=True, reason=str(row.get("reason", "")), since=ts_utc)}
    )


def _on_halt_cleared(state: LedgerState, _row: dict[str, Any], _ts: str, _cid: str) -> LedgerState:
    return state.model_copy(update={"halt": HaltView(active=False)})


def _on_kill_set(
    state: LedgerState, row: dict[str, Any], ts_utc: str, _correlation_id: str
) -> LedgerState:
    return state.model_copy(
        update={
            "kill_switch": KillSwitchView(
                active=True,
                source=str(row.get("origin", "")),
                since=ts_utc,
                flatten_requested=bool(row.get("flatten_requested", False)),
            )
        }
    )


def _on_kill_cleared(state: LedgerState, _row: dict[str, Any], _ts: str, _cid: str) -> LedgerState:
    return state.model_copy(update={"kill_switch": KillSwitchView(active=False)})


def _on_breaker_tripped(
    state: LedgerState, row: dict[str, Any], ts_utc: str, _correlation_id: str
) -> LedgerState:
    breakers = dict(state.breakers)
    breakers[str(row.get("breaker", "unknown"))] = BreakerView(state="open", since=ts_utc)
    return state.model_copy(update={"breakers": breakers})


def _on_breaker_reset(
    state: LedgerState, row: dict[str, Any], ts_utc: str, _correlation_id: str
) -> LedgerState:
    breakers = dict(state.breakers)
    breakers[str(row.get("breaker", "unknown"))] = BreakerView(state="closed", since=ts_utc)
    return state.model_copy(update={"breakers": breakers})


def _on_rollover(
    state: LedgerState, row: dict[str, Any], _ts_utc: str, _correlation_id: str
) -> LedgerState:
    return state.model_copy(
        update={
            "day_utc": str(row.get("day_utc", state.day_utc)),
            "day_start_equity_lamports": int(
                row.get("day_start_equity_lamports", state.day_start_equity_lamports)
            ),
            "counters": CountersView(),
        }
    )


def _on_approval(
    state: LedgerState, row: dict[str, Any], _ts_utc: str, _correlation_id: str
) -> LedgerState:
    approvals = dict(state.approvals)
    approval_id = str(row.get("id", ""))
    if approval_id:
        approvals[approval_id] = ApprovalView(
            kind=str(row.get("kind", "")), consumed=bool(row.get("consumed", False))
        )
    return state.model_copy(update={"approvals": approvals})


def _noop(state: LedgerState, _row: dict[str, Any], _ts: str, _cid: str) -> LedgerState:
    return state


_HANDLERS = {
    "PositionOpened": _on_position_opened,
    "PositionClosed": _on_position_closed,
    "FillRecorded": _on_fill,
    "OrderRejected": _on_rejected,
    "MarkToMarket": _on_mtm,
    "HaltSet": _on_halt_set,
    "HaltCleared": _on_halt_cleared,
    "KillSwitchSet": _on_kill_set,
    "KillSwitchCleared": _on_kill_cleared,
    "BreakerTripped": _on_breaker_tripped,
    "BreakerReset": _on_breaker_reset,
    "DailyRollover": _on_rollover,
    "ApprovalRecorded": _on_approval,
    "OrderPlaced": _noop,
    "ConfigChanged": _noop,
    "LiveWriteAttempted": _noop,
    "Escalation": _noop,
    "JournalNote": _noop,
}
