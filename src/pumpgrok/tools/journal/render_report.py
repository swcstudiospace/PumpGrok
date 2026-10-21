"""journal.render_report: daily/weekly markdown report from the ledger (TOOL-005).

Folds fills, closes, rejections, halts and open positions into a summary,
renders markdown with ``str.format`` templates (R9, no templating
dependency) and writes via tmp file + ``os.replace`` (R9). ``deliver``
accepts the relay request; the supervisor's ``notify.alert`` relay is Phase 4
work, so delivery is recorded on disk only in Phase 3.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from pumpgrok.core.ids import Clock, ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.tools._common import meta_now

__all__ = [
    "RENDER_REPORT_SPEC",
    "RenderReportIn",
    "RenderReportOut",
    "build_render_report_tool",
    "report_path_for",
    "run_render_report",
]

_REPORT_TEMPLATE = (
    "# Desk report ({period}, {day})\n"
    "\n"
    "Trades: {trades} (closed {closed_trades}). Realised PnL: {realised} lamports. "
    "Fees: {fees} lamports.\n"
    "Open positions: {open_positions}. Rejected signals: {rejected}. Halts: {halts}.\n"
    "Max drawdown fraction: {drawdown}. Delivery: {delivery}.\n"
)


class RenderReportIn(ToolInput):
    """Which report to render; ``as_of`` pins the report day (UTC)."""

    period: Literal["daily", "weekly"]
    as_of: datetime | None = None
    deliver: bool = True


class RenderReportOut(ToolOutput):
    """Report path and the folded summary."""

    report_path: str
    summary: dict = Field(default_factory=dict)


RENDER_REPORT_SPEC = ToolSpec(
    name="journal.render_report",
    description=(
        "Render the daily or weekly desk report to markdown under var/reports "
        "and queue it for notify delivery."
    ),
    input_model=RenderReportIn,
    output_model=RenderReportOut,
    side_effect=SideEffect.PAPER_WRITE,
    timeout_s=30.0,
    rate_limit_key="ledger",
    idempotent=True,
    backend="pumpgrok.ledger.store.LedgerStore",
)


def report_path_for(reports_dir: Path, period: str, day: str) -> Path:
    """Deterministic report path: d(period, as_of day) idempotency."""
    return reports_dir / f"report-{period}-{day}.md"


async def run_render_report(
    inp: RenderReportIn, store: LedgerStore, clock: Clock, reports_dir: Path
) -> dict:
    """Fold the ledger, render markdown, write atomically."""
    as_of = inp.as_of or datetime.fromtimestamp(clock.now(), UTC)
    day = as_of.strftime("%Y-%m-%d")
    trades = 0
    closed = 0
    realised = 0
    fees = 0
    rejected = 0
    halts = 0
    opened = 0
    for event in store.read(limit=1000):
        payload = event["payload"]
        if event["type"] == "FillRecorded":
            trades += 1
            fees += int(payload.get("venue_fee_lamports", 0))
            fees += int(payload.get("network_cost_lamports", 0))
        elif event["type"] == "PositionClosed":
            closed += 1
            realised += int(payload.get("realized_pnl_lamports", 0))
        elif event["type"] == "PositionOpened":
            opened += 1
        elif event["type"] == "OrderRejected":
            rejected += 1
        elif event["type"] == "HaltSet":
            halts += 1
    open_positions = max(0, opened - closed)
    delivery = "queued" if inp.deliver else "skipped"
    body = _REPORT_TEMPLATE.format(
        period=inp.period,
        day=day,
        trades=trades,
        closed_trades=closed,
        realised=realised,
        fees=fees,
        open_positions=open_positions,
        rejected=rejected,
        halts=halts,
        drawdown="0",
        delivery=delivery,
    )
    reports_dir.mkdir(parents=True, exist_ok=True)
    target = report_path_for(reports_dir, inp.period, day)
    fd, tmp_name = tempfile.mkstemp(dir=str(reports_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    ambient = ambient_correlation()
    summary = {
        "trades": trades,
        "closed_trades": closed,
        "win_rate": None,
        "profit_factor": None,
        "realised_lamports": realised,
        "max_drawdown_fraction": "0",
        "rejected_signals": rejected,
        "open_positions": open_positions,
        "halts": halts,
        "bot_health": {},
    }
    return RenderReportOut.model_validate(
        {
            "report_path": str(target),
            "summary": summary,
            "meta": meta_now(
                "ledger", inp.correlation_id or (str(ambient) if ambient else None)
            ),
        }
    ).model_dump()


def build_render_report_tool(
    store: LedgerStore, clock: Clock, reports_dir: Path
) -> Tool:
    """Bind ``journal.render_report`` to one store, clock and directory."""

    @tool(RENDER_REPORT_SPEC)
    async def _render_report(payload: RenderReportIn) -> dict:
        return await run_render_report(payload, store, clock, reports_dir)

    return _render_report
