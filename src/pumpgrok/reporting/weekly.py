"""Weekly report builder: Monday 00:15Z (paper-engine.md 8.1, 8.3).

Same window fold as the daily report over the ISO week starting Monday,
plus the per-day table and the live-gate threshold status. The gate section
lists each of the nine precondition ids with its current value and OK/unmet,
computed on ``source=paper`` events only through ``LiveGate.evaluate``.
"""

from __future__ import annotations

import os
from pathlib import Path

from pumpgrok.execution.live.live_gate import LiveGate
from pumpgrok.reporting.daily import DailyReport, day_next, read_events_readonly
from pumpgrok.reporting.render import ReportModel

_YMD_TEMPLATE = "{year:04d}-{month:02d}-{dom:02d}"
_PER_DAY_TEMPLATE = (
    "{day} | fills {fills} | closed {closed} | rejected {rejected} | events {events}"
)
_GATE_LINE_TEMPLATE = "{number} {gate_id} | {status} | {reason}"
_WEEK_RANGE_TEMPLATE = "{first} to {last}"


def _iso_monday(day: str) -> str:
    """Rewind a YYYY-MM-DD date to its Monday (pure calendar math)."""
    year, month, dom = (int(part) for part in day.split("-"))

    def weekday(y: int, m: int, d: int) -> int:
        # Sakamoto: 0 = Sunday.
        t = (0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4)
        yy = y - (1 if m < 3 else 0)
        return (yy + yy // 4 - yy // 100 + yy // 400 + t[m - 1] + d) % 7

    def shift(y: int, m: int, d: int, delta: int) -> tuple[int, int, int]:
        leap = y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
        lengths = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
        d += delta
        while d < 1:
            m -= 1
            if m < 1:
                m = 12
                y -= 1
            leap = y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
            lengths = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
            d += lengths[m - 1]
        while d > lengths[m - 1]:
            d -= lengths[m - 1]
            m += 1
            if m > 12:
                m = 1
                y += 1
            leap = y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
            lengths = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
        return (y, m, d)

    back = (weekday(year, month, dom) + 6) % 7
    y, m, d = shift(year, month, dom, -back)
    return _YMD_TEMPLATE.format(year=y, month=m, dom=d)


class WeeklyReport:
    """Builds the weekly ``ReportModel`` for the ISO week containing ``day``."""

    @staticmethod
    def build(
        ledger_path: Path,
        day: str,
        *,
        mode: str = "paper",
        autonomy: str = "autonomous-paper",
        root: Path | None = None,
    ) -> ReportModel:
        monday = _iso_monday(day)
        days: list[str] = [monday]
        cursor = monday
        for _ in range(6):
            cursor = day_next(cursor)[:10]
            days.append(cursor)
        week_start = monday + "T00:00:00Z"
        week_end = day_next(days[-1])

        events = read_events_readonly(ledger_path)
        week_events = [e for e in events if week_start <= str(e.get("ts_utc", "")) < week_end]
        fills = [e for e in week_events if e["type"] == "FillRecorded"]
        closed = [e for e in week_events if e["type"] == "PositionClosed"]
        rejected_total = sum(1 for e in week_events if e["type"] == "OrderRejected")

        per_day: list[str] = []
        for single in days:
            start = single + "T00:00:00Z"
            end = day_next(single)
            day_events = [e for e in week_events if start <= str(e.get("ts_utc", "")) < end]
            day_fills = sum(1 for e in day_events if e["type"] == "FillRecorded")
            day_closed = sum(1 for e in day_events if e["type"] == "PositionClosed")
            day_rejected = sum(1 for e in day_events if e["type"] == "OrderRejected")
            per_day.append(
                _PER_DAY_TEMPLATE.format(
                    day=single,
                    fills=day_fills,
                    closed=day_closed,
                    rejected=day_rejected,
                    events=len(day_events),
                )
            )

        base = DailyReport.build(ledger_path, days[-1], mode=mode, autonomy=autonomy)
        gate_root = root if root is not None else Path(os.environ.get("PUMPGROK_ROOT", "."))
        gate = LiveGate(mode="live", environ=dict(os.environ), root=gate_root)
        gate_lines = tuple(
            _GATE_LINE_TEMPLATE.format(
                number=item.number,
                gate_id=item.id,
                status="OK" if item.met else "unmet",
                reason=item.reason,
            )
            for item in gate.evaluate()
        )

        return ReportModel(
            period="weekly",
            day=_WEEK_RANGE_TEMPLATE.format(first=days[0], last=days[-1]),
            mode=base.mode,
            autonomy=base.autonomy,
            ledger_id=base.ledger_id,
            seq=base.seq,
            equity_start_lamports=base.equity_start_lamports,
            equity_end_lamports=base.equity_end_lamports,
            trades=len(fills),
            closed=len(closed),
            win_rate=base.win_rate,
            realized_lamports=base.realized_lamports,
            unrealized_lamports=base.unrealized_lamports,
            fees_venue_lamports=base.fees_venue_lamports,
            fees_network_lamports=base.fees_network_lamports,
            max_drawdown_pct=base.max_drawdown_pct,
            daily_loss_pct=base.daily_loss_pct,
            trade_rows=base.trade_rows,
            position_rows=base.position_rows,
            rejected=base.rejected
            or ((("rejected_total", rejected_total),) if rejected_total else ()),
            verdicts=base.verdicts,
            risk_events=base.risk_events,
            approvals_cleared=base.approvals_cleared,
            bot_health=base.bot_health,
            data_freshness=base.data_freshness,
            live_gate=gate_lines,
            unverified=base.unverified,
            per_day=tuple(per_day),
        )
