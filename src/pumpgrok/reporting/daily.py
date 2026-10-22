"""Daily report builder (paper-engine.md 8.1, 8.3).

``DailyReport.build`` folds the fixture ledger through the 04-01 views and
hands a pure ``ReportModel`` to the renderer. The ledger is opened read-only:
the path is guarded first and sqlite opens it with ``mode=ro``, because the
``LedgerStore`` constructor would create ``var/`` files as a side effect.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

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

_RO_URI_TEMPLATE = "file:{path}?mode=ro"
_SIGNED_PCT_TEMPLATE = "{value:+.2f}"
_PCT_TEMPLATE = "{value:.2f}"
_RISK_EVENT_TEMPLATE = "{etype} {ts} {cid}"
_APPROVAL_TEMPLATE = "ApprovalRecorded kind={kind} by={approved_by}"
_FROZEN_MTM_TEMPLATE = "frozen mtm positions: {count}"
_LAST_MTM_TEMPLATE = "last mtm: {ts}"
_MTM_POINTS_TEMPLATE = "mtm points: {count}"


def read_events_readonly(ledger_path: Path) -> list[dict[str, Any]]:
    """Read every tracked event without creating files.

    Returns [] when the ledger is absent (an empty desk still renders).
    Uses a read-only sqlite URI so neither the database nor ``var/`` is
    created; the ``LedgerStore`` constructor is deliberately not used here.
    """
    if not ledger_path.exists():
        return []
    uri = _RO_URI_TEMPLATE.format(path=ledger_path.resolve().as_posix())
    db = sqlite3.connect(uri, uri=True)
    try:
        rows = db.execute(
            "SELECT seq, ts_utc, source, correlation_id, idempotency_key,"
            " type, payload_json, prev_hash, hash FROM events ORDER BY seq ASC"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        db.close()
    events: list[dict[str, Any]] = []
    for seq, ts_utc, source, cid, key, type, payload_json, prev_hash, hash_ in rows:
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
    uri = _RO_URI_TEMPLATE.format(path=ledger_path.resolve().as_posix())
    db = sqlite3.connect(uri, uri=True)
    try:
        row = db.execute(
            "SELECT value FROM meta WHERE key = ?", ("initial_equity_lamports",)
        ).fetchone()
    except sqlite3.Error:
        return 0
    finally:
        db.close()
    if row is None:
        return RiskBudget().paper_equity_lamports
    return int(row[0])


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
    events: list[dict[str, Any]], genesis: LedgerState, start: str, end: str
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
            start_state = reduce(start_state, event)
        state = reduce(state, event)
        visible.append(event)
    return start_state, state, visible


def _closed_trade_rows(window: list[dict[str, Any]]) -> list[TradeRow]:
    rows: list[TradeRow] = []
    for event in window:
        if event["type"] != "PositionClosed":
            continue
        payload = event["payload"]
        pnl = int(payload.get("realized_pnl_lamports", 0))
        basis = int(payload.get("cost_basis_lamports", 0))
        pct = _SIGNED_PCT_TEMPLATE.format(value=pnl * 100.0 / basis) if basis else "n/a"
        rows.append(
            TradeRow(
                ticket=str(payload.get("ticket_id", "")),
                mint=str(payload.get("mint", ""))[:8],
                size_lamports=int(payload.get("size_lamports", 0)),
                reason=str(payload.get("reason", "")),
                pnl_lamports=pnl,
                pnl_pct=pct,
                fees_lamports=int(payload.get("fees_lamports", 0)),
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
        last = day if last_day is None else last_day
        events = read_events_readonly(ledger_path)
        start = day_start(day)
        end = day_next(last)
        window = [e for e in events if _in_window(str(e.get("ts_utc", "")), start, end)]
        genesis = initial_state(
            source="paper",
            initial_equity_lamports=read_initial_equity_readonly(ledger_path),
            day_utc=day,
        )
        start_state, state, visible = _fold_bounded(events, genesis, start, end)
        position_rows = _position_rows(state)
        closed = [e for e in window if e["type"] == "PositionClosed"]
        fills = [e for e in window if e["type"] == "FillRecorded"]
        ledger_id = str(events[0].get("correlation_id", "")) if events else ""
        seq = int(visible[-1]["seq"]) if visible else 0
        wr = win_rate(visible, since_ts=start, until_ts=end)
        dd = drawdown_fraction(state)

        return ReportModel(
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
            fees_network_lamports=0,
            max_drawdown_pct=_PCT_TEMPLATE.format(value=dd * 100),
            daily_loss_pct="0.00",
            trade_rows=tuple(_closed_trade_rows(window)),
            position_rows=position_rows,
            rejected=tuple(sorted(_rejected_counts(window).items())),
            verdicts=tuple(sorted(_verdict_counts(window).items())),
            risk_events=_risk_events(window),
            approvals_cleared=_approvals(window),
            bot_health=(),
            data_freshness=_data_freshness(visible),
            unverified=_unverified(window, position_rows),
        )
