"""Daily report builder (paper-engine.md 8.1, 8.3).

``DailyReport.build`` folds the fixture ledger through the 04-01 views and
hands a pure ``ReportModel`` to the renderer. The ledger is opened read-only:
the path is guarded first and sqlite opens it with ``mode=ro``, because the
``LedgerStore`` constructor would create ``var/`` files as a side effect.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from pumpgrok.backtest.roundtrip import (
    RoundTripFill,
    RoundTripsResult,
    group_round_trips,
    per_strategy_breakdown,
)
from pumpgrok.core.errors import CorruptState
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.reducer import LedgerState, initial_state, reduce
from pumpgrok.ledger.views import (
    drawdown_fraction,
    equity_lamports,
    fees_lamports,
    positions,
    realized_pnl_lamports,
    unrealized_pnl_lamports,
    win_rate,
)
from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.reporting.render import PositionRow, ReportModel, TradeRow
from pumpgrok.reporting.strategy_section import render_strategy_section

_RO_URI_TEMPLATE = "{uri}?mode=ro"
_SIGNED_PCT_TEMPLATE = "{value:+.2f}"
_PCT_TEMPLATE = "{value:.2f}"
_RISK_EVENT_TEMPLATE = "{etype} {ts} {cid}"
_APPROVAL_TEMPLATE = "ApprovalRecorded kind={kind} by={approved_by}"
_FROZEN_MTM_TEMPLATE = "frozen mtm positions: {count}"
_LAST_MTM_TEMPLATE = "last mtm: {ts}"
_MTM_POINTS_TEMPLATE = "mtm points: {count}"


def _valid_timestamp(value: object) -> bool:
    """True when ``ts_utc`` parses as an ISO-8601 timestamp with a UTC offset."""
    if not isinstance(value, str) or not value:
        return False
    try:
        parse_ts_utc(value)
    except ValueError:
        return False
    return True


def read_events_readonly(ledger_path: Path) -> list[dict[str, Any]]:
    """Read every tracked event without creating files.

    Returns [] when the ledger is absent (an empty desk still renders).
    Uses a read-only sqlite URI so neither the database nor ``var/`` is
    created; the ``LedgerStore`` constructor is deliberately not used here.
    """
    if not ledger_path.exists():
        return []
    uri = _RO_URI_TEMPLATE.format(uri=ledger_path.resolve().as_uri())
    db = sqlite3.connect(uri, uri=True)
    try:
        rows = db.execute(
            "SELECT seq, ts_utc, source, correlation_id, idempotency_key,"
            " type, payload_json, prev_hash, hash FROM events ORDER BY seq ASC"
        ).fetchall()
    finally:
        db.close()
    events: list[dict[str, Any]] = []
    for seq, ts_utc, source, cid, key, type, payload_json, prev_hash, hash_ in rows:
        if not _valid_timestamp(ts_utc):
            raise CorruptState(f"ledger event seq {seq} ({type}) has a missing or malformed ts_utc")
        try:
            payload = json.loads(payload_json)
        except ValueError:
            continue
        events.append(
            {
                "seq": seq,
                "ts_utc": ts_utc,
                "source": source,
                "correlation_id": cid,
                "idempotency_key": key,
                "type": type,
                "payload": payload,
                "prev_hash": prev_hash,
                "hash": hash_,
            }
        )
    return events


def read_initial_equity_readonly(ledger_path: Path) -> int:
    """Read the ledger's ``initial_equity_lamports`` meta row without writing.

    Returns 0 when the ledger file is absent (an empty desk). When the file exists but
    the row is absent, returns ``RiskBudget().paper_equity_lamports``, the same default
    the Supervisor uses for a missing row.
    """
    if not ledger_path.exists():
        return 0
    uri = _RO_URI_TEMPLATE.format(uri=ledger_path.resolve().as_uri())
    db = sqlite3.connect(uri, uri=True)
    try:
        row = db.execute(
            "SELECT value FROM meta WHERE key = ?", ("initial_equity_lamports",)
        ).fetchone()
    finally:
        db.close()
    if row is None:
        return RiskBudget().paper_equity_lamports
    return int(row[0])


def _has_table(db: sqlite3.Connection, table: str) -> bool:
    """True when the sidecar ``table`` exists (legacy ledgers may lack it)."""
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def read_deposits_readonly(ledger_path: Path) -> dict[int, int]:
    """Read the position_deposits sidecar (PositionOpened seq -> deposit) without writing.

    Returns {} when the ledger file is absent or no deposit was ever recorded (a legacy
    ledger), so the fold holds no deposit. The table is written by execution/deposits.py.
    """
    if not ledger_path.exists():
        return {}
    uri = _RO_URI_TEMPLATE.format(uri=ledger_path.resolve().as_uri())
    db = sqlite3.connect(uri, uri=True)
    try:
        if not _has_table(db, "position_deposits"):
            return {}
        rows = db.execute("SELECT opened_seq, deposit_lamports FROM position_deposits").fetchall()
    finally:
        db.close()
    return {int(seq): int(lamports) for seq, lamports in rows}


def read_ticket_refs_readonly(ledger_path: Path) -> dict[str, str]:
    """Read ticket-to-strategy refs without creating files.

    Returns {} when the ledger is absent, the sidecar is missing, or no ticket
    is attributed. An empty map means the period has no strategy rows.
    """
    if not ledger_path.exists():
        return {}
    uri = _RO_URI_TEMPLATE.format(uri=ledger_path.resolve().as_uri())
    db = sqlite3.connect(uri, uri=True)
    try:
        if not _has_table(db, "strategy_ticket_refs"):
            return {}
        rows = db.execute("SELECT ticket_id, strategy_id FROM strategy_ticket_refs").fetchall()
    finally:
        db.close()
    return {str(ticket): str(strategy) for ticket, strategy in rows}


def _inclusive_days(day: str, last: str) -> Decimal:
    """Inclusive UTC day count from ``day`` through ``last``."""
    count = 1
    cursor = day
    while cursor != last:
        cursor = day_next(cursor)[:10]
        count += 1
        if count > 4000:
            raise ValueError(f"report span {day} to {last} is not a calendar range")
    return Decimal(count)


_DAY_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_day(day: str) -> date:
    """The calendar date a YYYY-MM-DD string names; ValueError when it names no such day."""
    if not _DAY_PATTERN.fullmatch(day):
        raise ValueError(f"not a YYYY-MM-DD date: {day!r}")
    return date.fromisoformat(day)


def day_start(day: str) -> str:
    """UTC instant at which a YYYY-MM-DD day starts, in the ledger ``ts_utc`` form.

    Uses the six-digit fraction that ``format_ts_utc`` always writes, so string
    comparison of a fractional event against this boundary is correct at midnight.
    """
    return day + "T00:00:00.000000Z"


def day_next(day: str) -> str:
    """Next UTC day for a YYYY-MM-DD string (pure calendar math, no tz db)."""
    year, month, dom = (int(part) for part in day.split("-"))
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    lengths = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    dom += 1
    if dom > lengths[month - 1]:
        dom = 1
        month += 1
    if month > 12:
        month = 1
        year += 1
    return day_start(f"{year:04d}-{month:02d}-{dom:02d}")


def _in_window(ts: str, start: str, end: str) -> bool:
    return start <= ts < end


def _fold_bounded(
    events: list[dict[str, Any]],
    genesis: LedgerState,
    start: str,
    end: str,
    deposits: Mapping[int, int] | None = None,
) -> tuple[LedgerState, LedgerState, list[dict[str, Any]]]:
    """Fold only events before ``end``; return (state at ``start``, state at ``end``, visible).

    Keeps a report stable when later trades land: nothing at or after ``end`` is folded.
    """
    start_state = genesis
    state = genesis
    visible: list[dict[str, Any]] = []
    for event in events:
        ts = str(event.get("ts_utc", ""))
        if ts >= end:
            continue
        if ts < start:
            start_state = reduce(start_state, event, deposits)
        state = reduce(state, event, deposits)
        visible.append(event)
    return start_state, state, visible


def _ledger_money(event: dict[str, Any], key: str) -> int:
    """A required lamport figure on a ledger row. Absent or non-integer is corruption."""
    payload = event["payload"]
    if key not in payload:
        raise CorruptState(f"ledger event seq {event['seq']} ({event['type']}) has no {key}")
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise CorruptState(
            f"ledger event seq {event['seq']} ({event['type']}) has a non-integer {key}"
        )
    return value


def _closed_trade_rows(window: list[dict[str, Any]]) -> list[TradeRow]:
    rows: list[TradeRow] = []
    for event in window:
        if event["type"] != "PositionClosed":
            continue
        payload = event["payload"]
        proceeds = _ledger_money(event, "proceeds_lamports")
        pnl = _ledger_money(event, "realized_pnl_lamports")
        # The writers book realized P&L as proceeds less the net cost basis, so the
        # basis is recovered from the two figures the row records.
        basis = proceeds - pnl
        pct = (
            _SIGNED_PCT_TEMPLATE.format(value=Decimal(pnl) * 100 / Decimal(basis))
            if basis
            else "n/a"
        )
        rows.append(
            TradeRow(
                ticket=str(payload.get("ticket_id", "")),
                mint=str(payload.get("mint", ""))[:8],
                size_lamports=basis,
                reason=str(payload.get("reason", "")),
                pnl_lamports=pnl,
                pnl_pct=pct,
                fees_lamports=None,
                correlation_id=str(event.get("correlation_id", "")),
            )
        )
    return rows


def _position_rows(state: LedgerState) -> tuple[PositionRow, ...]:
    return tuple(
        PositionRow(
            mint=mint[:8],
            entry_lamports=int(pos.cost_basis_lamports),
            mtm_lamports=int(pos.last_mtm_lamports),
            unrealized_lamports=int(pos.last_mtm_lamports - pos.cost_basis_lamports),
            age="",
            mtm_source=pos.mtm_source,
            mtm_frozen=bool(pos.mtm_frozen),
        )
        for mint, pos in sorted(positions(state).items())
    )


def _rejected_counts(window: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in window:
        if event["type"] == "OrderRejected":
            reason = str(event["payload"].get("reason", "unknown"))
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def _verdict_counts(window: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in window:
        if event["type"] != "JournalNote":
            continue
        if event["payload"].get("note_kind") != "verdict":
            continue
        first = str(event["payload"].get("text", "")).split(None, 1)
        verdict = first[0].upper() if first else "unknown"
        if verdict not in ("CLEAR", "CONDITIONAL", "KILL", "BLIND"):
            verdict = "note"
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts


def _risk_events(window: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        _RISK_EVENT_TEMPLATE.format(
            etype=event["type"], ts=event.get("ts_utc", ""), cid=event.get("correlation_id", "")
        )
        for event in window
        if event["type"]
        in (
            "HaltSet",
            "HaltCleared",
            "KillSwitchSet",
            "KillSwitchCleared",
            "BreakerTripped",
            "BreakerReset",
            "Escalation",
        )
    )


def _approvals(window: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        _APPROVAL_TEMPLATE.format(
            kind=event["payload"].get("kind", ""),
            approved_by=event["payload"].get("approved_by", ""),
        )
        for event in window
        if event["type"] == "ApprovalRecorded"
    )


def _unverified(
    window: list[dict[str, Any]], position_rows: tuple[PositionRow, ...]
) -> tuple[str, ...]:
    frozen = [m for m in position_rows if m.mtm_frozen]
    return tuple([_FROZEN_MTM_TEMPLATE.format(count=len(frozen))] if frozen else []) + tuple(
        [
            "ledger_inconsistent day"
            for e in window
            if e["type"] == "Escalation" and e["payload"].get("kind") == "ledger_inconsistent"
        ]
    )


def _data_freshness(visible: list[dict[str, Any]]) -> tuple[str, ...]:
    mtm_ts = [str(e.get("ts_utc", "")) for e in visible if e["type"] == "MarkToMarket"]
    if not mtm_ts:
        return ()
    return (
        _LAST_MTM_TEMPLATE.format(ts=mtm_ts[-1]),
        _MTM_POINTS_TEMPLATE.format(count=len(mtm_ts)),
    )


def _loss_pct(start: int, end: int) -> str:
    """The day's loss as a percent of its starting equity; a gain reads 0.00."""
    if start <= 0:
        return "n/a"
    loss = max(start - end, 0)
    return _PCT_TEMPLATE.format(value=Decimal(loss) * 100 / Decimal(start))


def _read_events_once(db: sqlite3.Connection, _ledger_path: Path) -> list[dict[str, Any]]:
    """Every tracked event off the snapshot connection, with ts validation."""
    rows = db.execute(
        "SELECT seq, ts_utc, source, correlation_id, idempotency_key,"
        " type, payload_json, prev_hash, hash FROM events ORDER BY seq ASC"
    ).fetchall()
    events: list[dict[str, Any]] = []
    for seq, ts_utc, source, cid, key, type, payload_json, prev_hash, hash_ in rows:
        if not _valid_timestamp(ts_utc):
            raise CorruptState(f"ledger event seq {seq} ({type}) has a missing or malformed ts_utc")
        try:
            payload = json.loads(payload_json)
        except ValueError:
            continue
        events.append(
            {
                "seq": seq,
                "ts_utc": ts_utc,
                "source": source,
                "correlation_id": cid,
                "idempotency_key": key,
                "type": type,
                "payload": payload,
                "prev_hash": prev_hash,
                "hash": hash_,
            }
        )
    return events


def _read_deposits_once(db: sqlite3.Connection, _ledger_path: Path) -> dict[int, int]:
    """PositionOpened seq -> deposit; {} for a legacy ledger without the table."""
    if not _has_table(db, "position_deposits"):
        return {}
    rows = db.execute("SELECT opened_seq, deposit_lamports FROM position_deposits").fetchall()
    return {int(seq): int(lamports) for seq, lamports in rows}


def _read_equity_once(db: sqlite3.Connection, _ledger_path: Path) -> int:
    """The ``initial_equity_lamports`` meta row; the RiskBudget default when absent."""
    row = db.execute(
        "SELECT value FROM meta WHERE key = ?", ("initial_equity_lamports",)
    ).fetchone()
    if row is None:
        return RiskBudget().paper_equity_lamports
    return int(row[0])


def _read_refs_once(db: sqlite3.Connection, _ledger_path: Path) -> dict[str, str]:
    """Ticket-to-strategy refs; {} when the sidecar table is missing."""
    if not _has_table(db, "strategy_ticket_refs"):
        return {}
    rows = db.execute("SELECT ticket_id, strategy_id FROM strategy_ticket_refs").fetchall()
    return {str(ticket): str(strategy) for ticket, strategy in rows}


@dataclass(frozen=True)
class LedgerSnapshot:
    """The ledger rows a report reads, read once on one read-only connection."""

    events: list[dict[str, Any]]
    deposits: dict[int, int]
    initial_equity_lamports: int
    ticket_refs: dict[str, str]


def read_snapshot(ledger_path: Path) -> LedgerSnapshot:
    """Read the ledger once without creating files.

    An absent ledger reads as an empty desk. On an existing ledger any sqlite
    failure propagates; only the legacy sidecar tables may be missing, and a
    missing table reads as no rows.
    """
    if not ledger_path.exists():
        return LedgerSnapshot(events=[], deposits={}, initial_equity_lamports=0, ticket_refs={})
    uri = _RO_URI_TEMPLATE.format(uri=ledger_path.resolve().as_uri())
    db = sqlite3.connect(uri, uri=True)
    try:
        events = _read_events_once(db, ledger_path)
        deposits = _read_deposits_once(db, ledger_path)
        initial_equity_lamports = _read_equity_once(db, ledger_path)
        ticket_refs = _read_refs_once(db, ledger_path)
    finally:
        db.close()
    return LedgerSnapshot(events, deposits, initial_equity_lamports, ticket_refs)


class DailyReport:
    """Builds the ``ReportModel`` for UTC days ``day`` through ``last_day`` (inclusive)."""

    @staticmethod
    def build(
        ledger_path: Path,
        day: str,
        *,
        mode: str = "paper",
        autonomy: str = "autonomous-paper",
        last_day: str | None = None,
        snapshot: LedgerSnapshot | None = None,
    ) -> ReportModel:
        parse_day(day)
        if last_day is not None:
            parse_day(last_day)
        last = day if last_day is None else last_day
        snap = snapshot if snapshot is not None else read_snapshot(ledger_path)
        events = snap.events
        deposits = snap.deposits
        start = day_start(day)
        end = day_next(last)
        window = [e for e in events if _in_window(str(e.get("ts_utc", "")), start, end)]
        genesis = initial_state(
            source="paper",
            initial_equity_lamports=snap.initial_equity_lamports,
            day_utc=day,
        )
        start_state, state, visible = _fold_bounded(events, genesis, start, end, deposits)
        position_rows = _position_rows(state)
        closed = [e for e in window if e["type"] == "PositionClosed"]
        fills = [e for e in window if e["type"] == "FillRecorded"]
        ledger_id = str(events[0].get("correlation_id", "")) if events else ""
        seq = int(visible[-1]["seq"]) if visible else 0
        wr = win_rate(visible, since_ts=start, until_ts=end)
        dd = drawdown_fraction(state)

        model = ReportModel(
            period="daily",
            day=day,
            mode=mode,
            autonomy=autonomy,
            ledger_id=ledger_id,
            seq=seq,
            equity_start_lamports=equity_lamports(start_state),
            equity_end_lamports=equity_lamports(state),
            trades=len(fills),
            closed=len(closed),
            win_rate=str(wr) if wr is not None else "n/a",
            realized_lamports=realized_pnl_lamports(visible, since_ts=start, until_ts=end),
            unrealized_lamports=unrealized_pnl_lamports(state),
            fees_venue_lamports=fees_lamports(visible, since_ts=start, until_ts=end),
            fees_network_lamports=None,
            max_drawdown_pct=_PCT_TEMPLATE.format(value=dd * 100),
            daily_loss_pct=_loss_pct(equity_lamports(start_state), equity_lamports(state)),
            halt_limit_pct=_PCT_TEMPLATE.format(value=RiskBudget().daily_loss_halt_fraction * 100),
            trade_rows=tuple(_closed_trade_rows(window)),
            position_rows=position_rows,
            rejected=tuple(sorted(_rejected_counts(window).items())),
            verdicts=tuple(sorted(_verdict_counts(window).items())),
            risk_events=_risk_events(window),
            approvals_cleared=_approvals(window),
            bot_health=None,
            data_freshness=_data_freshness(visible),
            unverified=_unverified(window, position_rows),
            strategy_section=_strategy_section(snap.ticket_refs, events, day, last),
        )
        return model


def _strategy_fills(
    events: list[dict[str, Any]],
    refs: Mapping[str, str],
    start: str,
    end: str,
) -> list[RoundTripFill]:
    """Window fills keyed by mint, each attributed to its PositionOpened ticket."""
    fills: list[RoundTripFill] = []
    ticket_by_mint: dict[str, str] = {}
    pending_buys: dict[str, list[int]] = {}
    for event in sorted(events, key=lambda item: int(item.get("seq", 0))):
        payload_raw = event.get("payload")
        payload = dict(payload_raw) if isinstance(payload_raw, Mapping) else {}
        event_type = event.get("type")
        if event_type == "PositionOpened":
            ticket = str(payload.get("ticket_id", ""))
            mint = str(payload.get("mint", ""))
            if not ticket:
                continue
            ticket_by_mint[mint] = ticket
            for index in pending_buys.pop(mint, []):
                previous = fills[index]
                fills[index] = RoundTripFill(
                    key=previous.key,
                    side=previous.side,
                    lamports=previous.lamports,
                    strategy_id=refs.get(ticket, "unattributed"),
                )
            continue
        if event_type != "FillRecorded" or not (start <= str(event.get("ts_utc", "")) < end):
            continue
        side = str(payload.get("side", ""))
        if side not in ("buy", "sell"):
            continue
        mint = str(payload.get("mint", ""))
        ticket = ticket_by_mint.get(mint, "")
        lamports = abs(int(payload.get("cash_delta_lamports", 0)))
        strategy = refs.get(ticket, "unattributed") if ticket else "unattributed"
        fills.append(
            RoundTripFill(
                key=mint or ticket or "unknown",
                side=side,
                lamports=lamports,
                strategy_id=strategy,
            )
        )
        if side == "buy" and not ticket:
            pending_buys.setdefault(mint, []).append(len(fills) - 1)
    return fills


def _strategy_win_stats(result: RoundTripsResult) -> tuple[dict[str, float], dict[str, int]]:
    trip_counts: dict[str, int] = {}
    wins: dict[str, int] = {}
    for trip in result.trips:
        if trip.unclosed:
            continue
        trip_counts[trip.strategy_id] = trip_counts.get(trip.strategy_id, 0) + 1
        if trip.realized_net_lamports > 0:
            wins[trip.strategy_id] = wins.get(trip.strategy_id, 0) + 1
    win_rates = {
        strategy: wins.get(strategy, 0) / count
        for strategy, count in trip_counts.items()
        if count > 0
    }
    return win_rates, trip_counts


def _strategy_section(
    refs: dict[str, str],
    events: list[dict[str, Any]],
    day: str,
    last: str,
) -> str:
    """The period's strategy section, or "" when no strategy row exists."""
    if not refs:
        return ""
    fills = _strategy_fills(events, refs, day_start(day), day_next(last))
    result = group_round_trips(fills)
    breakdown = per_strategy_breakdown(result)
    if not breakdown or set(breakdown) == {"unattributed"}:
        return ""
    win_rates, trip_counts = _strategy_win_stats(result)
    return render_strategy_section(breakdown, win_rates, trip_counts)
