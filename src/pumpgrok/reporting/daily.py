"""Daily report builder (paper-engine.md 8.1, 8.3).

``DailyReport.build`` folds the fixture ledger through the 04-01 views and
hands a pure ``ReportModel`` to the renderer. The ledger is opened read-only:
the path is guarded first and sqlite opens it with ``mode=ro``, because the
``LedgerStore`` constructor would create ``var/`` files as a side effect.
``read_snapshot`` reads everything a report needs in one pass, so the weekly
report folds its daily and per-day figures from the same rows.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

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
from pumpgrok.reporting.render import PositionRow, ReportModel, TradeRow
from pumpgrok.reporting.strategy_section import section_from_events

_DAY_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_SIGNED_PCT_TEMPLATE = "{value:+.2f}"
_PCT_TEMPLATE = "{value:.2f}"
_RISK_EVENT_TEMPLATE = "{etype} {ts} {cid}"
_APPROVAL_TEMPLATE = "ApprovalRecorded kind={kind} by={approved_by}"
_FROZEN_MTM_TEMPLATE = "frozen mtm positions: {count}"
_LAST_MTM_TEMPLATE = "last mtm: {ts}"
_MTM_POINTS_TEMPLATE = "mtm points: {count}"


@dataclass(frozen=True)
class LedgerSnapshot:
    """The ledger rows a report reads, read once on one read-only connection."""

    events: list[dict[str, Any]]
    deposits: dict[int, int]
    initial_equity_lamports: int
    ticket_refs: dict[str, str]


def _ro_uri(ledger_path: Path) -> str:
    """A read-only sqlite URI whose percent-encoded path cannot be read as a query."""
    return ledger_path.resolve().as_uri() + "?mode=ro"


def read_snapshot(ledger_path: Path) -> LedgerSnapshot:
    """Read the ledger once without creating files.

    An absent ledger reads as an empty desk. On an existing ledger any sqlite
    failure propagates; only the legacy sidecar tables may be missing, and a
    missing table reads as no rows.
    """
    if not ledger_path.exists():
        return LedgerSnapshot(events=[], deposits={}, initial_equity_lamports=0, ticket_refs={})
    db = sqlite3.connect(_ro_uri(ledger_path), uri=True)
    try:
        return LedgerSnapshot(
            events=_read_events(db),
            deposits=_read_deposits(db),
            initial_equity_lamports=_read_initial_equity(db),
            ticket_refs=_read_ticket_refs(db),
        )
    finally:
        db.close()


def _has_table(db: sqlite3.Connection, name: str) -> bool:
    row = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _read_events(db: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT seq, ts_utc, source, correlation_id, idempotency_key,"
        " type, payload_json, prev_hash, hash FROM events ORDER BY seq ASC"
    ).fetchall()
    events: list[dict[str, Any]] = []
    for seq, ts_utc, source, cid, key, type_, payload_json, prev_hash, hash_ in rows:
        _checked_ts(seq, ts_utc)
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
                "type": type_,
                "payload": payload,
                "prev_hash": prev_hash,
                "hash": hash_,
            }
        )
    return events


def _checked_ts(seq: int, ts_utc: str) -> None:
    """Refuse a ledger row whose timestamp cannot place it in a report window."""
    try:
        parsed = datetime.fromisoformat(ts_utc)
    except (TypeError, ValueError) as exc:
        raise CorruptState(f"ledger event seq {seq} has no usable ts_utc: {ts_utc!r}") from exc
    if parsed.tzinfo is None:
        raise CorruptState(f"ledger event seq {seq} ts_utc has no UTC offset: {ts_utc!r}")


def _read_initial_equity(db: sqlite3.Connection) -> int:
    """The ``initial_equity_lamports`` meta row; the RiskBudget default when it is absent."""
    row = db.execute(
        "SELECT value FROM meta WHERE key = ?", ("initial_equity_lamports",)
    ).fetchone()
    if row is None:
        return RiskBudget().paper_equity_lamports
    return int(row[0])


def _read_deposits(db: sqlite3.Connection) -> dict[int, int]:
    """PositionOpened seq -> deposit. A legacy ledger has no position_deposits table."""
    if not _has_table(db, "position_deposits"):
        return {}
    rows = db.execute("SELECT opened_seq, deposit_lamports FROM position_deposits").fetchall()
    return {int(seq): int(lamports) for seq, lamports in rows}


def _read_ticket_refs(db: sqlite3.Connection) -> dict[str, str]:
    """Ticket -> strategy. A ledger without the strategy sidecar has no strategy rows."""
    if not _has_table(db, "strategy_ticket_refs"):
        return {}
    rows = db.execute("SELECT ticket_id, strategy_id FROM strategy_ticket_refs").fetchall()
    return {str(ticket): str(strategy) for ticket, strategy in rows}


def parse_day(day: str) -> date:
    """The calendar date a YYYY-MM-DD string names; ValueError when it names no such day."""
    if not _DAY_PATTERN.fullmatch(day):
        raise ValueError(f"not a YYYY-MM-DD date: {day!r}")
    return date.fromisoformat(day)


def _inclusive_days(day: str, last: str) -> Decimal:
    """Inclusive UTC day count from ``day`` through ``last``."""
    span = (parse_day(last) - parse_day(day)).days
    if span < 0:
        raise ValueError(f"report span {day} to {last} is not a calendar range")
    return Decimal(span + 1)


def day_start(day: str) -> str:
    """UTC instant at which a YYYY-MM-DD day starts, in the ledger ``ts_utc`` form.

    Uses the six-digit fraction that ``format_ts_utc`` always writes, so string
    comparison of a fractional event against this boundary is correct at midnight.
    """
    return parse_day(day).isoformat() + "T00:00:00.000000Z"


def day_next(day: str) -> str:
    """Next UTC day for a YYYY-MM-DD string (calendar arithmetic, no tz db)."""
    return day_start((parse_day(day) + timedelta(days=1)).isoformat())


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
        ts = event["ts_utc"]
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
            etype=event["type"], ts=event["ts_utc"], cid=event.get("correlation_id", "")
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
    mtm_ts = [e["ts_utc"] for e in visible if e["type"] == "MarkToMarket"]
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
    ) -> ReportModel:
        return DailyReport.from_snapshot(
            read_snapshot(ledger_path), day, mode=mode, autonomy=autonomy, last_day=last_day
        )

    @staticmethod
    def from_snapshot(
        snapshot: LedgerSnapshot,
        day: str,
        *,
        mode: str = "paper",
        autonomy: str = "autonomous-paper",
        last_day: str | None = None,
    ) -> ReportModel:
        """Fold a snapshot already read from the ledger into the period's report."""
        first = parse_day(day).isoformat()
        last = parse_day(day if last_day is None else last_day).isoformat()
        events = snapshot.events
        start = day_start(first)
        end = day_next(last)
        window = [e for e in events if _in_window(e["ts_utc"], start, end)]
        genesis = initial_state(
            source="paper",
            initial_equity_lamports=snapshot.initial_equity_lamports,
            day_utc=first,
        )
        start_state, state, visible = _fold_bounded(events, genesis, start, end, snapshot.deposits)
        position_rows = _position_rows(state)
        closed = [e for e in window if e["type"] == "PositionClosed"]
        fills = [e for e in window if e["type"] == "FillRecorded"]
        ledger_id = str(events[0].get("correlation_id", "")) if events else ""
        seq = int(visible[-1]["seq"]) if visible else 0
        wr = win_rate(visible, since_ts=start, until_ts=end)
        dd = drawdown_fraction(state)
        equity_start = equity_lamports(start_state)
        equity_end = equity_lamports(state)

        model = ReportModel(
            period="daily",
            day=first,
            mode=mode,
            autonomy=autonomy,
            ledger_id=ledger_id,
            seq=seq,
            equity_start_lamports=equity_start,
            equity_end_lamports=equity_end,
            trades=len(fills),
            closed=len(closed),
            win_rate=str(wr) if wr is not None else "n/a",
            realized_lamports=realized_pnl_lamports(visible, since_ts=start, until_ts=end),
            unrealized_lamports=unrealized_pnl_lamports(state),
            fees_venue_lamports=fees_lamports(visible, since_ts=start, until_ts=end),
            # Network cost is folded into fees_venue; no separate network figure is kept.
            fees_network_lamports=None,
            max_drawdown_pct=_PCT_TEMPLATE.format(value=dd * 100),
            daily_loss_pct=_loss_pct(equity_start, equity_end),
            halt_limit_pct=_PCT_TEMPLATE.format(value=RiskBudget().daily_loss_halt_fraction * 100),
            trade_rows=tuple(_closed_trade_rows(window)),
            position_rows=position_rows,
            rejected=tuple(sorted(_rejected_counts(window).items())),
            verdicts=tuple(sorted(_verdict_counts(window).items())),
            risk_events=_risk_events(window),
            approvals_cleared=_approvals(window),
            # Heartbeats are not written to the ledger, so bot health is not tracked.
            bot_health=None,
            data_freshness=_data_freshness(visible),
            unverified=_unverified(window, position_rows),
            strategy_section=_strategy_section(snapshot, first, last),
        )
        return model


def _strategy_section(snapshot: LedgerSnapshot, day: str, last: str) -> str:
    """The period's strategy section, or "" when no strategy row exists."""
    if not snapshot.ticket_refs:
        return ""
    return section_from_events(
        snapshot.events,
        snapshot.ticket_refs,
        start=day_start(day),
        end=day_next(last),
        elapsed_days=_inclusive_days(day, last),
        initial_equity_lamports=snapshot.initial_equity_lamports,
        deposits=snapshot.deposits,
    )
