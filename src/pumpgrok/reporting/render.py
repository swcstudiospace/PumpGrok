"""ASCII markdown renderer for paper reports (paper-engine.md 8.3, R9).

``str.format`` templates only; no jinja2 or other format-string library.
Every emitted document is verified ASCII-only before return.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from pumpgrok.core.units import split_lamports


def sol(lamports: int) -> str:
    """Render an integer lamport amount as SOL with 9 decimals (render time only)."""
    neg = "-" if lamports < 0 else ""
    whole, frac = split_lamports(lamports)
    return _SOL_TEMPLATE.format(neg=neg, whole=whole, frac=frac)


def assert_ascii(body: str) -> str:
    """Fail closed when a report would carry a non-ASCII byte."""
    try:
        body.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(_NON_ASCII_MESSAGE.format(detail=exc)) from exc
    return body


def cell(value: str) -> str:
    """Free text for one Markdown table cell: pipes escaped, line breaks flattened."""
    return _flat(value).replace("|", "\\|")


def _flat(value: str) -> str:
    """Free text kept to one line."""
    return value.replace("\r", " ").replace("\n", " ")


@dataclass(frozen=True)
class TradeRow:
    """One closed position for the trades table (all money in lamports)."""

    ticket: str = ""
    mint: str = ""
    size_lamports: int = 0
    reason: str = ""
    pnl_lamports: int = 0
    pnl_pct: str = "n/a"
    # None when the closing record does not carry fees; rendered as "not tracked".
    fees_lamports: int | None = None
    correlation_id: str = ""


@dataclass(frozen=True)
class PositionRow:
    """One open position for the open-positions table."""

    mint: str = ""
    entry_lamports: int = 0
    mtm_lamports: int = 0
    unrealized_lamports: int = 0
    age: str = ""
    mtm_source: str = ""
    mtm_frozen: bool = False


@dataclass(frozen=True)
class ReportModel:
    """Pure report data: no I/O, built by daily.py / weekly.py from ledger rows."""

    period: str = "daily"
    day: str = ""
    mode: str = "paper"
    autonomy: str = "autonomous-paper"
    ledger_id: str = ""
    seq: int = 0
    equity_start_lamports: int = 0
    equity_end_lamports: int = 0
    trades: int = 0
    closed: int = 0
    win_rate: str = "n/a"
    realized_lamports: int = 0
    unrealized_lamports: int = 0
    fees_venue_lamports: int = 0
    # None when the ledger does not track network fees separately; rendered "not tracked".
    fees_network_lamports: int | None = None
    max_drawdown_pct: str = "0.00"
    daily_loss_pct: str = "n/a"
    halt_limit_pct: str = "n/a"
    trade_rows: tuple[TradeRow, ...] = ()
    position_rows: tuple[PositionRow, ...] = ()
    rejected: tuple[tuple[str, int], ...] = ()
    verdicts: tuple[tuple[str, int], ...] = ()
    risk_events: tuple[str, ...] = ()
    approvals_cleared: tuple[str, ...] = ()
    # None when heartbeats are not tracked; an empty tuple when tracked and none recorded.
    bot_health: tuple[str, ...] | None = None
    data_freshness: tuple[str, ...] = ()
    live_gate: tuple[str, ...] = ()
    unverified: tuple[str, ...] = ()
    per_day: tuple[str, ...] = ()
    # The per-strategy section, appended after the report body; "" when there is none.
    strategy_section: str = ""


_SUMMARY_TEMPLATE = (
    "## Summary\n"
    "trades (buys/sells): {trades} | closed: {closed} | win rate: {win_rate}\n"
    "realized PnL: {realized} SOL | unrealized PnL: {unrealized} SOL\n"
    "fees: venue {fees_venue} SOL + network {fees_network}\n"
    "equity start: {equity_start} SOL | equity end: {equity_end} SOL ({equity_pct} since start)\n"
    "max drawdown: {drawdown} % | daily loss: {daily_loss} % (halt at {halt_limit} %)\n"
)

_TRADES_HEADER = (
    "## Trades\nticket | mint | size SOL | reason | pnl SOL | pnl % | "
    "fees lamports | correlation_id\n"
)
_TRADES_ROW = "{ticket} | {mint} | {size} | {reason} | {pnl} | {pnl_pct} | {fees} | {cid}\n"
_TRADES_EMPTY = "## Trades\nnone closed in this window\n"

_POSITIONS_HEADER = (
    "## Open positions\nmint | entry SOL | mtm SOL | unrealized SOL | "
    "age | mtm_source | mtm_frozen\n"
)
_POSITIONS_ROW = "{mint} | {entry} | {mtm} | {unrealized} | {age} | {source} | {frozen}\n"
_POSITIONS_EMPTY = "## Open positions\nnone open\n"

_REJECTED_HEADER = "## Rejected signals\nreason | count\n"
_REJECTED_ROW = "{reason} | {count}\n"
_REJECTED_EMPTY = "## Rejected signals\nnone\n"

_VERDICTS_HEADER = "## Safety outcomes\nverdict | count\n"
_VERDICTS_ROW = "{verdict} | {count}\n"
_VERDICTS_EMPTY = "## Safety outcomes\nno verdicts recorded\n"

_RISK_HEADER = "## Risk events\n"
_RISK_ROW = "- {event}\n"
_RISK_EMPTY = "## Risk events\nnone\n"

_APPROVALS_HEADER = "## Approvals\n"
_APPROVAL_ROW = "- {event}\n"
_APPROVALS_EMPTY = "## Approvals\nnone\n"

_HEALTH_HEADER = (
    "## Bot health\nseat | cycles | crashes | restarts | observe_only | p50_s | p95_s\n"
)
_HEALTH_ROW = "{line}\n"
_HEALTH_EMPTY = "## Bot health\nno heartbeat rows recorded\n"
_HEALTH_UNTRACKED = "## Bot health\nnot tracked\n"

_FRESHNESS_HEADER = "## Data freshness\n"
_FRESHNESS_ROW = "- {line}\n"
_FRESHNESS_EMPTY = "## Data freshness\nno market ticks recorded\n"

_GATE_HEADER = "## Live gate\nid | status | value\n"
_GATE_ROW = "{line}\n"
_GATE_ABSENT = "## Live gate\ndaily report: see the weekly report for gate status\n"

_UNVERIFIED_HEADER = "## Unverified\n"
_UNVERIFIED_ROW = "- {line}\n"
_UNVERIFIED_EMPTY = "## Unverified\nnone: every figure derives from curve prices\n"

_PER_DAY_HEADER = (
    "## Per day\n(segment totals; positions opened one day and closed the next "
    "split unrealized/realized across days)\n"
)
_PER_DAY_ROW = "{line}\n"
_PER_DAY_EMPTY = "## Per day\nno per-day rows\n"
_SOL_TEMPLATE = "{neg}{whole}.{frac:09d}"
_NON_ASCII_MESSAGE = "report is not ASCII-only: {detail}"
_SIGNED_PCT_TEMPLATE = "{value:+.2f}"
_DAILY_TITLE = "# PumpGrok paper report - daily - {day} (UTC)\n"
_MODE_LINE = (
    "Mode: {mode} | Autonomy: {autonomy} | Ledger: {ledger} seq {seq} | Equity: {equity} SOL\n"
)


def _equity_pct(model: ReportModel) -> str:
    if not model.equity_start_lamports:
        return "n/a"
    change = model.equity_end_lamports - model.equity_start_lamports
    pct = Decimal(change) * 100 / Decimal(model.equity_start_lamports)
    return _SIGNED_PCT_TEMPLATE.format(value=pct)


def _fees_network(model: ReportModel) -> str:
    if model.fees_network_lamports is None:
        return "not tracked"
    return f"{sol(model.fees_network_lamports)} SOL"


def _section_tail(model: ReportModel) -> str:
    return "\n" + model.strategy_section if model.strategy_section else ""


def render_daily(model: ReportModel) -> str:
    """Render the daily markdown document (paper-engine.md 8.3)."""
    return assert_ascii(_daily_body(model) + _section_tail(model))


def _daily_body(model: ReportModel) -> str:
    """The daily document without its strategy section."""
    parts = [
        _DAILY_TITLE.format(day=model.day),
        _MODE_LINE.format(
            mode=model.mode,
            autonomy=model.autonomy,
            ledger=model.ledger_id,
            seq=model.seq,
            equity=sol(model.equity_end_lamports),
        ),
        "\n",
        _SUMMARY_TEMPLATE.format(
            trades=model.trades,
            closed=model.closed,
            win_rate=model.win_rate,
            realized=sol(model.realized_lamports),
            unrealized=sol(model.unrealized_lamports),
            fees_venue=sol(model.fees_venue_lamports),
            fees_network=_fees_network(model),
            equity_start=sol(model.equity_start_lamports),
            equity_end=sol(model.equity_end_lamports),
            equity_pct=_equity_pct(model),
            drawdown=model.max_drawdown_pct,
            daily_loss=model.daily_loss_pct,
            halt_limit=model.halt_limit_pct,
        ),
        "\n",
    ]
    if model.trade_rows:
        parts.append(_TRADES_HEADER)
        for row in model.trade_rows:
            parts.append(
                _TRADES_ROW.format(
                    ticket=cell(row.ticket or "-"),
                    mint=cell(row.mint),
                    size=sol(row.size_lamports),
                    reason=cell(row.reason or "-"),
                    pnl=sol(row.pnl_lamports),
                    pnl_pct=row.pnl_pct,
                    fees="not tracked" if row.fees_lamports is None else str(row.fees_lamports),
                    cid=cell(row.correlation_id or "-"),
                )
            )
    else:
        parts.append(_TRADES_EMPTY)
    parts.append("\n")
    parts.append(_render_positions(model))
    parts.append("\n")
    parts.append(_render_rejected(model))
    parts.append("\n")
    parts.append(_render_verdicts(model))
    parts.append("\n")
    parts.append(_render_risk_events(model))
    parts.append("\n")
    parts.append(_render_approvals(model))
    parts.append("\n")
    parts.append(_render_health(model))
    parts.append("\n")
    parts.append(_render_freshness(model))
    parts.append("\n")
    parts.append(_GATE_ABSENT)
    parts.append("\n")
    parts.append(_render_unverified(model))
    return "".join(parts)


def render_weekly(model: ReportModel) -> str:
    """Render the weekly markdown: daily shape plus per-day table and live gate."""
    daily = _daily_body(model).replace(
        "# PumpGrok paper report - daily -", "# PumpGrok paper report - weekly -", 1
    )
    insert: list[str] = []
    if model.per_day:
        insert.append(_PER_DAY_HEADER)
        for line in model.per_day:
            insert.append(_PER_DAY_ROW.format(line=line))
    else:
        insert.append(_PER_DAY_EMPTY)
    insert.append("\n")
    if model.live_gate:
        insert.append(_GATE_HEADER)
        for line in model.live_gate:
            insert.append(_GATE_ROW.format(line=line))
    else:
        insert.append("## Live gate\nno gate evaluation recorded\n")
    insert.append("\n")
    body = daily.replace(_GATE_ABSENT, "".join(insert), 1)
    return assert_ascii(body + _section_tail(model))


def _render_positions(model: ReportModel) -> str:
    if not model.position_rows:
        return _POSITIONS_EMPTY
    parts = [_POSITIONS_HEADER]
    for row in model.position_rows:
        parts.append(
            _POSITIONS_ROW.format(
                mint=cell(row.mint),
                entry=sol(row.entry_lamports),
                mtm=sol(row.mtm_lamports),
                unrealized=sol(row.unrealized_lamports),
                age=cell(row.age or "-"),
                source=cell(row.mtm_source or "-"),
                frozen="true" if row.mtm_frozen else "false",
            )
        )
    return "".join(parts)


def _render_rejected(model: ReportModel) -> str:
    if not model.rejected:
        return _REJECTED_EMPTY
    parts = [_REJECTED_HEADER]
    for reason, count in model.rejected:
        parts.append(_REJECTED_ROW.format(reason=cell(reason), count=count))
    return "".join(parts)


def _render_verdicts(model: ReportModel) -> str:
    if not model.verdicts:
        return _VERDICTS_EMPTY
    parts = [_VERDICTS_HEADER]
    for verdict, count in model.verdicts:
        parts.append(_VERDICTS_ROW.format(verdict=verdict, count=count))
    return "".join(parts)


def _render_risk_events(model: ReportModel) -> str:
    if not model.risk_events:
        return _RISK_EMPTY
    parts = [_RISK_HEADER]
    for event in model.risk_events:
        parts.append(_RISK_ROW.format(event=_flat(event)))
    return "".join(parts)


def _render_approvals(model: ReportModel) -> str:
    if not model.approvals_cleared:
        return _APPROVALS_EMPTY
    parts = [_APPROVALS_HEADER]
    for approval in model.approvals_cleared:
        parts.append(_APPROVAL_ROW.format(event=_flat(approval)))
    return "".join(parts)


def _render_health(model: ReportModel) -> str:
    if model.bot_health is None:
        return _HEALTH_UNTRACKED
    if not model.bot_health:
        return _HEALTH_EMPTY
    parts = [_HEALTH_HEADER]
    for line in model.bot_health:
        parts.append(_HEALTH_ROW.format(line=line))
    return "".join(parts)


def _render_freshness(model: ReportModel) -> str:
    if not model.data_freshness:
        return _FRESHNESS_EMPTY
    parts = [_FRESHNESS_HEADER]
    for line in model.data_freshness:
        parts.append(_FRESHNESS_ROW.format(line=line))
    return "".join(parts)


def _render_unverified(model: ReportModel) -> str:
    if not model.unverified:
        return _UNVERIFIED_EMPTY
    parts = [_UNVERIFIED_HEADER]
    for line in model.unverified:
        parts.append(_UNVERIFIED_ROW.format(line=line))
    return "".join(parts)


def field_names() -> tuple[str, ...]:
    """Snapshot helper: every section header the renderer can emit."""
    return (
        "Summary",
        "Trades",
        "Open positions",
        "Rejected signals",
        "Safety outcomes",
        "Risk events",
        "Bot health",
        "Data freshness",
        "Live gate",
        "Unverified",
    )
