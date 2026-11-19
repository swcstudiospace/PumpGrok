"""Weekly report builder: Monday 00:15Z (paper-engine.md 8.1, 8.3).

Same window fold as the daily report over the ISO week starting Monday,
plus the per-day table and the live-gate threshold status. The gate section
lists each of the nine precondition ids with its current value and OK/unmet,
computed on ``source=paper`` events only through ``LiveGate.evaluate``.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from pumpgrok.execution.live.live_gate import LiveGate
from pumpgrok.reporting.daily import DailyReport, day_next, day_start, parse_day, read_snapshot
from pumpgrok.reporting.render import ReportModel, cell

# The only environment variable LiveGate reads; nothing else reaches the gate.
_GATE_ENVIRONMENT = ("PUMPGROK_LIVE_ENABLE",)
_PER_DAY_TEMPLATE = (
    "{day} | fills {fills} | closed {closed} | rejected {rejected} | events {events}"
)
_GATE_LINE_TEMPLATE = "{number} {gate_id} | {status} | {reason}"
_WEEK_RANGE_TEMPLATE = "{first} to {last}"


class WeeklyReport:
    """Builds the weekly ``ReportModel`` for the ISO week containing ``day``."""

    @staticmethod
    def build(
        ledger_path: Path,
        day: str,
        *,
        mode: str = "paper",
        autonomy: str = "autonomous-paper",
        root: Path,
        now: str | None = None,
    ) -> ReportModel:
        first = parse_day(day)
        monday = first - timedelta(days=first.weekday())
        days = [(monday + timedelta(days=offset)).isoformat() for offset in range(7)]
        week_start = day_start(days[0])
        week_end = day_next(days[-1])

        snapshot = read_snapshot(ledger_path)
        week_events = [e for e in snapshot.events if week_start <= e["ts_utc"] < week_end]
        fills = [e for e in week_events if e["type"] == "FillRecorded"]
        closed = [e for e in week_events if e["type"] == "PositionClosed"]
        rejected_total = sum(1 for e in week_events if e["type"] == "OrderRejected")

        per_day: list[str] = []
        for single in days:
            start = day_start(single)
            end = day_next(single)
            day_events = [e for e in week_events if start <= e["ts_utc"] < end]
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

        base = DailyReport.from_snapshot(
            snapshot, days[0], mode=mode, autonomy=autonomy, last_day=days[-1]
        )
        environ = {name: os.environ[name] for name in _GATE_ENVIRONMENT if name in os.environ}
        gate = LiveGate(mode="live", environ=environ, root=root)
        gate_lines = tuple(
            _GATE_LINE_TEMPLATE.format(
                number=item.number,
                gate_id=item.id,
                status="OK" if item.met else "unmet",
                reason=cell(item.reason),
            )
            for item in gate.evaluate(now=now if now is not None else day)
        )

        model = ReportModel(
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
            halt_limit_pct=base.halt_limit_pct,
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
            strategy_section=base.strategy_section,
        )
        return model
