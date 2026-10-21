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

from pumpgrok.ledger.reducer import initial_state, reduce
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


def read_events_readonly(ledger_path: Path) -> list[dict[str, Any]]:
    """Read every tracked event without creating files.

    Returns [] when the ledger is absent (an empty desk still renders).
    Uses a read-only sqlite URI so neither the database nor ``var/`` is
    created; the ``LedgerStore`` constructor is deliberately not used here.
    """
    if not ledger_path.exists():
        return []
    uri = "file:{0}?mode=ro".format(ledger_path.resolve().as_posix())
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
    return "{0:04d}-{1:02d}-{2:02d}T00:00:00Z".format(year, month, dom)


def _in_window(ts: str, start: str, end: str) -> bool:
    return start <= ts < end


class DailyReport:
    """Builds the daily ``ReportModel`` for one UTC day."""

    @staticmethod
    def build(
        ledger_path: Path,
        day: str,
        *,
        mode: str = "paper",
        autonomy: str = "autonomous-paper",
    ) -> ReportModel:
        events = read_events_readonly(ledger_path)
        start = day + "T00:00:00Z"
        end = day_next(day)
        window = [e for e in events if _in_window(str(e.get("ts_utc", "")), start, end)]

        state = initial_state(source="paper", initial_equity_lamports=0, day_utc=day)
        for event in events:
            state = reduce(state, event)
        genesis_equity = int(state.peak_equity_lamports) or int(state.cash_lamports)

        closed_rows: list[TradeRow] = []
        for event in window:
            if event["type"] != "PositionClosed":
                continue
            payload = event["payload"]
            pnl = int(payload.get("realized_pnl_lamports", 0))
            basis = int(payload.get("cost_basis_lamports", 0))
            pct = "{0:+.2f}".format(pnl * 100.0 / basis) if basis else "n/a"
            closed_rows.append(
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

        position_rows = tuple(
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

        rejected_counts: dict[str, int] = {}
        for event in window:
            if event["type"] == "OrderRejected":
                reason = str(event["payload"].get("reason", "unknown"))
                rejected_counts[reason] = rejected_counts.get(reason, 0) + 1

        verdict_counts: dict[str, int] = {}
        for event in window:
            if event["type"] != "JournalNote":
                continue
            if event["payload"].get("note_kind") != "verdict":
                continue
            first = str(event["payload"].get("text", "")).split(None, 1)
            verdict = first[0].upper() if first else "unknown"
            if verdict not in ("CLEAR", "CONDITIONAL", "KILL", "BLIND"):
                verdict = "note"
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

        risk_events = tuple(
            "{0} {1} {2}".format(
                event["type"], event.get("ts_utc", ""), event.get("correlation_id", "")
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
        approvals = tuple(
            "ApprovalRecorded kind={0} by={1}".format(
                event["payload"].get("kind", ""), event["payload"].get("approved_by", "")
            )
            for event in window
            if event["type"] == "ApprovalRecorded"
        )

        frozen = [m for m in position_rows if m.mtm_frozen]
        unverified = tuple(
            ["frozen mtm positions: {0}".format(len(frozen))] if frozen else []
        ) + tuple(
            [
                "ledger_inconsistent day"
                for e in window
                if e["type"] == "Escalation" and e["payload"].get("kind") == "ledger_inconsistent"
            ]
        )

        mtm_ts = [str(e.get("ts_utc", "")) for e in events if e["type"] == "MarkToMarket"]
        freshness = (
            ("last mtm: {0}".format(mtm_ts[-1]), "mtm points: {0}".format(len(mtm_ts)))
            if mtm_ts
            else ()
        )

        wr = win_rate(events, since_ts=start, until_ts=end)
        closed = [e for e in window if e["type"] == "PositionClosed"]
        fills = [e for e in window if e["type"] == "FillRecorded"]
        ledger_id = ""
        if events:
            ledger_id = str(events[0].get("correlation_id", ""))
        seq = int(events[-1]["seq"]) if events else 0
        dd = drawdown_fraction(state)
        realized = realized_pnl_lamports(events, since_ts=start, until_ts=end)
        fees = fees_lamports(events, since_ts=start, until_ts=end)

        return ReportModel(
            period="daily",
            day=day,
            mode=mode,
            autonomy=autonomy,
            ledger_id=ledger_id,
            seq=seq,
            equity_start_lamports=genesis_equity,
            equity_end_lamports=equity_lamports(state) if events else 0,
            trades=len(fills),
            closed=len(closed),
            win_rate=str(wr) if wr is not None else "n/a",
            realized_lamports=realized,
            unrealized_lamports=unrealized_pnl_lamports(state) if events else 0,
            fees_venue_lamports=fees,
            fees_network_lamports=0,
            max_drawdown_pct="{0:.2f}".format(dd * 100),
            daily_loss_pct="0.00",
            trade_rows=tuple(closed_rows),
            position_rows=position_rows,
            rejected=tuple(sorted(rejected_counts.items())),
            verdicts=tuple(sorted(verdict_counts.items())),
            risk_events=risk_events,
            approvals_cleared=approvals,
            bot_health=(),
            data_freshness=freshness,
            unverified=unverified,
        )
