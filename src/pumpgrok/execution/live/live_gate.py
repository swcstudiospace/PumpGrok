"""The nine live preconditions, in order (paper-engine.md 7.2, R21, R31).

`LiveGate.evaluate()` reports every precondition, met or not; it never stops at the first
unmet one. `LiveGate.check()` returns the ids of the unmet ones, in order. The CLI runs the
gate whenever the effective mode is live and exits 3 before any other work.

Fail closed: this release has no wallet allowlist or notional cap setting, no
confirmation verifier, no adapter implementation and no readable halt, kill-switch or
breaker state. Preconditions 5 to 9 therefore report unmet with the reason naming what
is missing. Precondition 8 is always unmet by design. Preconditions 3 and 4 are
computed on ledger events with source=paper only; any source=replay row refuses the
metrics (F-B1, R21).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pumpgrok.replay.clock import WallClock

MIN_PAPER_DAYS = 14
MIN_CLOSED_TRADES = 50
MIN_PROFIT_FACTOR = 1.2
MAX_DRAWDOWN_FRACTION = 0.15

PRECONDITION_IDS: tuple[str, ...] = (
    "mode_live",
    "live_enable_env",
    "min_paper_days",
    "performance_thresholds",
    "wallet_allowlist",
    "notional_cap",
    "confirmation_record",
    "adapter_registered",
    "no_active_stop",
)


@dataclass(frozen=True)
class Precondition:
    number: int
    id: str
    met: bool
    reason: str


class LiveGate:
    """Evaluates R21 against the effective mode, the environment and the working directory."""

    def __init__(self, *, mode: str, environ: Mapping[str, str], root: Path) -> None:
        self._mode = mode
        self._environ = environ
        self._root = root

    def evaluate(self) -> tuple[Precondition, ...]:
        confirmation = self._root / "var" / "live_confirmation.json"
        mode_live = self._mode == "live"
        env_enabled = self._environ.get("PUMPGROK_LIVE_ENABLE", "").strip() == "1"
        days_met, days_reason, perf_met, perf_reason = _paper_window(self._root)
        mode_reason = "effective mode is live" if mode_live else f"effective mode is {self._mode}"
        rows: tuple[tuple[bool, str], ...] = (
            (mode_live, mode_reason),
            (
                env_enabled,
                "PUMPGROK_LIVE_ENABLE=1" if env_enabled else "PUMPGROK_LIVE_ENABLE is not 1",
            ),
            (days_met, days_reason),
            (perf_met, perf_reason),
            (False, "live.wallet_allowlist is not a setting in this release"),
            (False, "live.notional_cap_sol is not a setting in this release"),
            (
                False,
                "var/live_confirmation.json missing"
                if not confirmation.exists()
                else "confirmation record verifier is not built in this release",
            ),
            (False, "no live adapter implementation ships in this release"),
            (False, "halt, kill switch and breaker state are not readable in this release"),
        )
        return tuple(
            Precondition(number=index, id=name, met=met, reason=reason)
            for index, (name, (met, reason)) in enumerate(
                zip(PRECONDITION_IDS, rows, strict=True), start=1
            )
        )

    def check(self) -> list[str]:
        """Ids of every unmet precondition, in R21 order. Empty means the gate is open."""
        return [item.id for item in self.evaluate() if not item.met]


def _paper_window(root: Path) -> tuple[bool, str, bool, str]:
    """Preconditions 3 and 4 from source=paper ledger events only.

    Read-only: guards the path and opens sqlite with ``mode=ro`` so the check
    never creates ``var/`` files. Any ``source=replay`` row refuses both
    metrics (a FixtureClock must never fabricate the paper window).
    """
    rows = _read_gate_rows(root / "var" / "ledger.sqlite")
    if rows is None:
        reason = "no source=paper ledger at var/ledger.sqlite"
        return (False, reason, False, reason)
    if any(source == "replay" for source, _, _, _ in rows):
        reason = "replay ledger: metrics refuse source=replay rows"
        return (False, reason, False, reason)
    paper = [(ts, type, payload) for source, ts, type, payload in rows if source == "paper"]
    if not paper:
        reason = "no source=paper events in var/ledger.sqlite"
        return (False, reason, False, reason)
    return (*_paper_days(paper), *_paper_perf(paper))


def _read_gate_rows(ledger: Path) -> list[tuple[str, str, str, str]] | None:
    """Raw gate rows, or None when the ledger is absent or unreadable."""
    if not ledger.exists():
        return None
    try:
        uri = f"file:{ledger.resolve().as_posix()}?mode=ro"
        db = sqlite3.connect(uri, uri=True)
        try:
            return list(
                db.execute(
                    "SELECT source, ts_utc, type, payload_json FROM events ORDER BY seq ASC"
                ).fetchall()
            )
        finally:
            db.close()
    except sqlite3.Error:
        return None


def _paper_days(paper: list[tuple[str, str, str]]) -> tuple[bool, str]:
    """Precondition 3: elapsed UTC days since the first source=paper event."""
    first_day = str(paper[0][0])[:10]
    today = datetime.fromtimestamp(WallClock().now(), UTC).strftime("%Y-%m-%d")
    span = datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(first_day, "%Y-%m-%d")
    days = max(0, span.days)
    reason = f"{days} of {MIN_PAPER_DAYS} days on source=paper events"
    return (days >= MIN_PAPER_DAYS, reason)


def _paper_perf(paper: list[tuple[str, str, str]]) -> tuple[bool, str]:
    """Precondition 4: closed count, profit factor and drawdown on paper rows."""
    closed = 0
    gains = 0
    losses = 0
    peak = 0
    equity = 0
    for _, type, payload_json in paper:
        try:
            payload = json.loads(str(payload_json))
        except ValueError:
            continue
        closed, gains, losses, peak, equity = _fold_perf_row(
            type, payload, closed=closed, gains=gains, losses=losses, peak=peak, equity=equity
        )
    drawdown = (peak - equity) / peak if peak else 0.0
    profit_factor = gains / losses if losses else (float("inf") if gains else 0.0)
    met = (
        closed >= MIN_CLOSED_TRADES
        and profit_factor >= MIN_PROFIT_FACTOR
        and drawdown <= MAX_DRAWDOWN_FRACTION
    )
    reason = (
        f"closed {closed}, pf {profit_factor:.2f}, dd {drawdown * 100:.1f} % on source=paper events"
    )
    return (met, reason)


def _fold_perf_row(
    type: str,
    payload: dict[str, Any],
    *,
    closed: int,
    gains: int,
    losses: int,
    peak: int,
    equity: int,
) -> tuple[int, int, int, int, int]:
    """Fold one paper row into the performance accumulators."""
    if type == "PositionClosed":
        pnl = int(payload.get("realized_pnl_lamports", 0))
        return (closed + 1, gains + max(pnl, 0), losses - min(pnl, 0), peak, equity)
    if type == "MarkToMarket":
        equity = int(payload.get("equity_lamports", equity))
        return (closed, gains, losses, max(peak, equity), equity)
    return (closed, gains, losses, peak, equity)


def refusal_lines(preconditions: Sequence[Precondition]) -> list[str]:
    """The stderr block for a refused live start: one [x]/[ ] line per precondition."""
    unmet = [item for item in preconditions if not item.met]
    lines = [
        f"LIVE GATE: refusing to start in mode=live. {len(unmet)} of "
        f"{len(preconditions)} preconditions unmet:"
    ]
    for item in preconditions:
        mark = "x" if item.met else " "
        lines.append(f"  [{mark}] {item.number} {item.id} {item.reason}")
    lines.append("Fix every unmet line or run in mode=paper. No transaction was attempted.")
    return lines
