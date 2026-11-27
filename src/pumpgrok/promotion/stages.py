"""Promotion stages as ledger rows: BACKTEST, PAPER, LIVE_ELIGIBLE (PRM-01, PRM-03, PRM-06).

Stages BACKTEST, PAPER and LIVE_ELIGIBLE are ledger rows (JournalNote
verdicts), one per strategy, each carrying the strategy version id, the
parameter-set hash, the evidence run id and the deciding metrics
snapshot. LIVE is derived from LIVE_ELIGIBLE plus the arm record and is
never stored (V4-11). Every transition appends to a decision log row
with the evidence id, the triggering event id and the previous stage.

Each stage change is one PromotionStageSet row with its decision log. The current stage is
folded from those rows; nothing is held in memory. A strategy moves one stage at a time.

Every step runs the one upgrade gate: upgrade.gate.evaluate_candidate is called once per advance.
This module runs no search and defines no check of its own. Every gate input about paper is built
from this strategy alone: its fills, its positions and its marks. The backtest MetricsReport is
supplied by the caller, since it comes from the holdout run.

Attribution follows strategies/attribution.py. A row's ticket is its explicit ticket_id, else the
open ticket for its mint. PositionOpened opens a mint's ticket and PositionClosed clears it. A
FillRecorded names only its mint, so it takes the open ticket for that mint. A buy fill that
arrives before the PositionOpened it opens is held for that mint and claimed by the open. This
differs from attribution.py, which leaves such a fill in the unattributed bucket: a promotion
window must count the fill that opened the strategy's position. The strategy's window starts at
its first PositionOpened on one of its tickets. A window with no attributable fill is refused.

Drawdown follows LiveGate's formula (live_gate.py:197-216, fold 231-241): peak ratchets over
marked equity and drawdown = (peak - equity) / peak at window end. Marked equity at each
MarkToMarket row is the strategy's realized proceeds plus the marked value of its open positions,
read from that row's prices_json (mtm_lamports per held mint). Peak starts at the cost basis the
strategy deployed. A zero-loss record is refused before the gate.

A stage change needs a human: or gate: writer. Its parameter set must be the active set, and
that set's stored content must verify before the row is written. Only ``is_writer`` callers write,
and stored content is verified before use; a non-writer caller raises instead of writing (PRM-06).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pumpgrok.backtest.metrics import MetricsContext, summarize
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.ledger.active_set import is_writer, read_active_set, verify_stored_content
from pumpgrok.ledger.ticket_refs import load_refs
from pumpgrok.promotion.thresholds import PaperRecord, PromotionThresholds, evaluate_paper_record
from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.upgrade.gate import evaluate_candidate
from pumpgrok.upgrade.window_metrics import fills_from_rows

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pumpgrok.backtest.harness import HarnessResult
    from pumpgrok.backtest.metrics import MetricsReport
    from pumpgrok.core.adapter import Fill
    from pumpgrok.ledger.store import LedgerStore
    from pumpgrok.upgrade.bounds import Bounds
    from pumpgrok.upgrade.gate import GateVerdict
    from pumpgrok.upgrade.params import ParamSet

__all__ = [
    "Stage",
    "StageRefused",
    "StageRow",
    "advance_stage",
    "append_stage",
    "append_stage_row",
    "append_transition",
    "current_stage",
    "decision_log",
    "last_stage_row",
    "lower_stage",
    "paper_record",
    "paper_window",
    "read_stage_row",
    "require_writer",
    "stage_rows",
]


STAGE_PREFIX = "PROMOTION stage="
TRANSITION_PREFIX = "PROMOTION transition "


class Stage(StrEnum):
    """The three promotion stages, lowest first. LIVE is derived, never stored."""

    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE_ELIGIBLE = "LIVE_ELIGIBLE"


@dataclass(frozen=True)
class StageRow:
    """One strategy's stage row: stage plus the evidence it rests on."""

    strategy_id: str
    stage: Stage
    version_id: str = ""
    param_hash: str = ""
    evidence_run_id: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Transition:
    """One decision-log entry: the move, its evidence and its trigger."""

    strategy_id: str
    previous_stage: Stage | None
    next_stage: Stage
    evidence_id: str
    event_id: str


def _row_text(row: StageRow) -> str:
    metrics = json.dumps(row.metrics, sort_keys=True, separators=(",", ":"))
    return (
        f"{STAGE_PREFIX}{row.stage.value} strategy={row.strategy_id} "
        f"version={row.version_id} param={row.param_hash} run={row.evidence_run_id} "
        f"metrics={metrics}"
    )


def append_stage_row(
    store: LedgerStore,
    row: StageRow,
    *,
    by: str,
    ts_utc: str,
    source: str = "paper",
    correlation_id: str = "desk",
) -> None:
    """Append one stage row; raises unless ``by`` is a writer (PRM-06)."""
    if not is_writer(by):
        raise ValueError(f"promotion stage write refused: {by!r} is not a writer")
    store.append(
        ts_utc=ts_utc,
        source=source,
        correlation_id=correlation_id,
        idempotency_key=f"promotion|{row.strategy_id}|{row.stage.value}|{ts_utc}",
        type="JournalNote",
        payload={
            "source": source,
            "seat": "gate:promotion",
            "note_kind": "verdict",
            "text": _row_text(row),
            "refs": [],
        },
    )


def read_stage_row(store: LedgerStore, strategy_id: str) -> StageRow | None:
    """Latest stage row for one strategy, or None when never promoted."""
    row: StageRow | None = None
    for event in store.read(types=["JournalNote"], limit=None):
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if str(payload.get("note_kind", "")) != "verdict":
            continue
        text = str(payload.get("text", ""))
        if not text.startswith(STAGE_PREFIX):
            continue
        fields = dict(part.split("=", 1) for part in text.split(" ")[1:] if "=" in part)
        if fields.get("strategy") != strategy_id:
            continue
        try:
            stage = Stage(fields["stage"])
        except ValueError:
            continue
        try:
            metrics = json.loads(fields.get("metrics", "{}"))
        except ValueError:
            metrics = {}
        row = StageRow(
            strategy_id=strategy_id,
            stage=stage,
            version_id=fields.get("version", ""),
            param_hash=fields.get("param", ""),
            evidence_run_id=fields.get("run", ""),
            metrics=metrics if isinstance(metrics, dict) else {},
        )
    return row


def append_transition(
    store: LedgerStore,
    transition: Transition,
    *,
    by: str,
    ts_utc: str,
    source: str = "paper",
    correlation_id: str = "desk",
) -> None:
    """Append one decision-log row; writer-gated like stage rows."""
    if not is_writer(by):
        raise ValueError(f"promotion transition write refused: {by!r} is not a writer")
    previous = transition.previous_stage.value if transition.previous_stage is not None else "NONE"
    store.append(
        ts_utc=ts_utc,
        source=source,
        correlation_id=correlation_id,
        idempotency_key=(
            f"promotion-transition|{transition.strategy_id}|{previous}|"
            f"{transition.next_stage.value}|{ts_utc}"
        ),
        type="JournalNote",
        payload={
            "source": source,
            "seat": "gate:promotion",
            "note_kind": "verdict",
            "text": (
                f"{TRANSITION_PREFIX}"
                f"stage={transition.next_stage.value} "
                f"strategy={transition.strategy_id} from={previous} "
                f"evidence={transition.evidence_id} event={transition.event_id}"
            ),
            "refs": [],
        },
    )


def decision_log(store: LedgerStore, strategy_id: str) -> list[Transition]:
    """Every recorded transition for one strategy, oldest first."""
    log: list[Transition] = []
    for event in store.read(types=["JournalNote"], limit=None):
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if str(payload.get("note_kind", "")) != "verdict":
            continue
        text = str(payload.get("text", ""))
        if not text.startswith(TRANSITION_PREFIX):
            continue
        fields = dict(part.split("=", 1) for part in text.split(" ")[1:] if "=" in part)
        if fields.get("strategy") != strategy_id:
            continue
        try:
            next_stage = Stage(fields["stage"])
        except (KeyError, ValueError):
            continue
        previous_raw = fields.get("from", "NONE")
        previous = None if previous_raw == "NONE" else Stage(previous_raw)
        log.append(
            Transition(
                strategy_id=strategy_id,
                previous_stage=previous,
                next_stage=next_stage,
                evidence_id=fields.get("evidence", ""),
                event_id=fields.get("event", ""),
            )
        )
    return log


_UP: dict[Stage, Stage] = {Stage.BACKTEST: Stage.PAPER, Stage.PAPER: Stage.LIVE_ELIGIBLE}
_DOWN: dict[Stage, Stage] = {upper: lower for lower, upper in _UP.items()}


class StageRefused(ValueError):
    """A stage change the rules refuse: writer, step, gate verdict, or paper record."""


def require_writer(by: object) -> None:
    """Refuse unless ``by`` is a human: or gate: writer."""
    if not is_writer(by):
        raise StageRefused(f"stage change needs a human: or gate: writer, got {by!r}")


def lower_stage(stage: Stage) -> Stage | None:
    """The stage one step below, or None at BACKTEST."""
    return _DOWN.get(stage)


def stage_rows(store: LedgerStore, strategy_id: str) -> list[dict[str, Any]]:
    """Every PromotionStageSet row for one strategy written by a writer, oldest first.

    A row whose ``by`` is not a human: or gate: writer never folds into the stage, the same rule
    the active-set and autonomy readers apply.
    """
    return [
        event
        for event in store.read(types=["PromotionStageSet"], limit=None)
        if event["payload"].get("strategy_id") == strategy_id
        and is_writer(event["payload"].get("by"))
    ]


def last_stage_row(store: LedgerStore, strategy_id: str) -> dict[str, Any] | None:
    """The newest PromotionStageSet row for one strategy, or None when it has none."""
    rows = stage_rows(store, strategy_id)
    return rows[-1] if rows else None


def current_stage(store: LedgerStore, strategy_id: str) -> Stage:
    """The stage the ledger rows fold to; BACKTEST when the strategy has no row."""
    row = last_stage_row(store, strategy_id)
    return Stage.BACKTEST if row is None else Stage(row["payload"]["to_stage"])


def _days_between(start: str, now: str) -> int:
    span = datetime.strptime(str(now)[:10], "%Y-%m-%d") - datetime.strptime(start[:10], "%Y-%m-%d")
    return max(0, span.days)


def _marked_lamports(payload: Mapping[str, Any]) -> dict[str, int]:
    """Mint to marked lamports from one MarkToMarket prices_json; unusable entries are skipped."""
    try:
        prices = json.loads(str(payload.get("prices_json", "") or "{}"))
    except ValueError:
        return {}
    if not isinstance(prices, dict):
        return {}
    marks: dict[str, int] = {}
    for mint, mark in prices.items():
        value = mark.get("mtm_lamports") if isinstance(mark, dict) else None
        if isinstance(value, int) and not isinstance(value, bool):
            marks[str(mint)] = value
    return marks


@dataclass
class _Fold:
    """One strategy's paper window, folded from its own attributed rows."""

    window_start: str = ""
    deployed: int = 0
    closed_proceeds: int = 0
    equity: int = 0
    peak_path: int = 0
    pnls: list[int] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    curve: list[int] = field(default_factory=list)
    unpointed: int = 0


@dataclass
class _Tracks:
    """Open tickets, held positions, marks and fills awaiting their open, keyed by mint."""

    open_ticket: dict[str, str] = field(default_factory=dict)
    held: dict[str, int] = field(default_factory=dict)
    marks: dict[str, int] = field(default_factory=dict)
    awaiting: dict[str, list[Fill]] = field(default_factory=dict)
    tickets: set[str] = field(default_factory=set)


def _flush_points(fold: _Fold) -> None:
    """Give every attributed fill still without a point the current equity."""
    if fold.unpointed:
        fold.curve.extend([fold.equity] * fold.unpointed)
        fold.unpointed = 0


def _settle(fold: _Fold, tracks: _Tracks) -> None:
    """Update equity and the peak from the current state, then flush the pending points."""
    fold.equity = fold.closed_proceeds + sum(tracks.marks[m] for m in tracks.held)
    fold.peak_path = max(fold.peak_path, fold.equity)
    _flush_points(fold)


def _on_fill(fold: _Fold, tracks: _Tracks, row: Mapping[str, Any], mint: str) -> None:
    """Attribute one fill: to the open ticket on its mint, or hold it until that mint opens."""
    fill = fills_from_rows([row])[0][0]
    owner = tracks.open_ticket.get(mint)
    if owner is None:
        tracks.awaiting.setdefault(mint, []).append(fill)
    elif owner in tracks.tickets:
        fold.fills.append(fill)
        fold.unpointed += 1


def _on_open(
    fold: _Fold,
    tracks: _Tracks,
    payload: Mapping[str, Any],
    mint: str,
    ts_utc: str,
) -> None:
    """Open a mint's ticket; a strategy's open starts its window and claims the held fills."""
    ticket = str(payload.get("ticket_id", ""))
    tracks.open_ticket[mint] = ticket
    claimed = tracks.awaiting.pop(mint, [])
    if ticket not in tracks.tickets:
        return
    cost = int(payload.get("cost_basis_lamports", 0))
    fold.window_start = fold.window_start or ts_utc
    fold.deployed += cost
    tracks.held[mint] = cost
    tracks.marks[mint] = cost
    fold.fills.extend(claimed)
    fold.unpointed += len(claimed)


def _on_close(fold: _Fold, tracks: _Tracks, payload: Mapping[str, Any], mint: str) -> None:
    """Clear a mint's ticket; a close of a held position books its realized P&L."""
    tracks.open_ticket.pop(mint, None)
    tracks.awaiting.pop(mint, None)
    if mint not in tracks.held:
        return
    fold.pnls.append(int(payload.get("realized_pnl_lamports", 0)))
    fold.closed_proceeds += int(payload.get("proceeds_lamports", 0))
    del tracks.held[mint]
    tracks.marks.pop(mint, None)


def _on_mark(tracks: _Tracks, payload: Mapping[str, Any]) -> None:
    """Take the marks of held positions from one MarkToMarket row."""
    for marked_mint, value in _marked_lamports(payload).items():
        if marked_mint in tracks.held:
            tracks.marks[marked_mint] = value


def _fold_strategy(store: LedgerStore, strategy_id: str) -> _Fold:
    """Fold the paper rows into the strategy's window; other strategies' rows never count."""
    tickets = {ticket for ticket, sid in load_refs(store).items() if sid == strategy_id}
    rows = store.read(
        types=["PositionOpened", "PositionClosed", "MarkToMarket", "FillRecorded"],
        source="paper",
        limit=None,
    )
    tracks = _Tracks(tickets=tickets)
    fold = _Fold()
    for row in rows:
        payload = row["payload"]
        kind = row["type"]
        mint = str(payload.get("mint", ""))
        if kind == "FillRecorded":
            _on_fill(fold, tracks, row, mint)
            continue
        if kind == "PositionOpened":
            _on_open(fold, tracks, payload, mint, str(row["ts_utc"]))
        elif kind == "PositionClosed":
            _on_close(fold, tracks, payload, mint)
        else:
            _on_mark(tracks, payload)
        if fold.window_start:
            _settle(fold, tracks)
    _flush_points(fold)
    return fold


def _record(fold: _Fold, now_ts: str) -> PaperRecord:
    peak = max(fold.deployed, fold.peak_path)
    return PaperRecord(
        window_start=fold.window_start,
        paper_days=_days_between(fold.window_start, now_ts),
        closed_trades=len(fold.pnls),
        gains_lamports=sum(pnl for pnl in fold.pnls if pnl > 0),
        losses_lamports=-sum(pnl for pnl in fold.pnls if pnl < 0),
        max_drawdown_fraction=(peak - fold.equity) / peak if peak > 0 else 0.0,
    )


def paper_record(store: LedgerStore, strategy_id: str, *, now_ts: str) -> PaperRecord | None:
    """The strategy's paper record over its window, or None when it has no paper position."""
    fold = _fold_strategy(store, strategy_id)
    if not fold.window_start:
        return None
    return _record(fold, now_ts)


def paper_window(
    store: LedgerStore, strategy_id: str, *, now_ts: str
) -> tuple[PaperRecord, MetricsReport]:
    """The strategy's paper record and its own window MetricsReport.

    The report summarizes only this strategy's attributed fills, over the curve of its marked
    equity. A strategy with no attributable fill is refused, so its window never reaches the gate.
    """
    fold = _fold_strategy(store, strategy_id)
    if not fold.fills:
        raise StageRefused(
            f"strategy {strategy_id} has no paper fill: no attributable paper fill in its window"
        )
    if len(fold.curve) != len(fold.fills):
        raise StageRefused(f"strategy {strategy_id} window fills and marks do not line up")
    elapsed = (parse_ts_utc(now_ts) - parse_ts_utc(fold.window_start)) / 86400
    report = summarize(
        fold.fills,
        MetricsContext(
            initial_equity_lamports=fold.deployed,
            equity_curve_lamports=tuple(fold.curve),
            elapsed_days=Decimal(str(max(0.0, elapsed))),
        ),
    )
    return _record(fold, now_ts), report


def _key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _evidence_hash(verdict: GateVerdict, params_hash: str) -> str:
    binding = {"reason": verdict.reason, "detail": verdict.detail, "params_hash": params_hash}
    return hashlib.sha256(canonical_json(binding).encode("utf-8")).hexdigest()


def append_stage(
    store: LedgerStore,
    strategy_id: str,
    *,
    from_stage: Stage,
    to_stage: Stage,
    decision: str,
    by: str,
    params_hash: str,
    paper_window_start: str,
    evidence_hash: str,
    ts_utc: str,
    source: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Append one PromotionStageSet row and return it. Callers check the writer and the step."""
    row: dict[str, Any] = {
        "ts_utc": ts_utc,
        "source": source,
        "correlation_id": correlation_id,
        "idempotency_key": _key(
            "PromotionStageSet", strategy_id, str(from_stage), str(to_stage), ts_utc
        ),
        "type": "PromotionStageSet",
        "payload": {
            "source": source,
            "strategy_id": strategy_id,
            "from_stage": str(from_stage),
            "to_stage": str(to_stage),
            "decision": decision,
            "by": by,
            "params_hash": params_hash,
            "paper_window_start": paper_window_start,
            "evidence_hash": evidence_hash,
        },
    }
    store.append(**row)
    return row


def advance_stage(
    store: LedgerStore,
    strategy_id: str,
    *,
    params: ParamSet,
    bounds: Bounds,
    search: HarnessResult,
    run_id: str,
    backtest: MetricsReport,
    by: str,
    now_ts: str,
    thresholds: PromotionThresholds,
    ts_utc: str,
    source: str = "paper",
    correlation_id: str = "promotion",
) -> dict[str, Any]:
    """Move one strategy up one stage; return the row written.

    Refused, with nothing written, unless the writer is human: or gate:, the strategy has a stage
    above it, params is the active set with stored content, the strategy has an attributable paper
    window, and its paper record is not zero-loss. The step to LIVE_ELIGIBLE also needs the paper
    record to meet thresholds. Then evaluate_candidate runs once, against this strategy's own
    paper MetricsReport, and its verdict must be eligible.
    """
    if not strategy_id:
        raise StageRefused("a stage change needs a strategy id")
    require_writer(by)
    current = current_stage(store, strategy_id)
    target = _UP.get(current)
    if target is None:
        raise StageRefused(f"strategy {strategy_id} is already {current.value}: nothing above it")
    params_hash = params.content_hash
    if read_active_set(store) != params_hash:
        raise StageRefused("params is not the active parameter set; activate the candidate")
    verify_stored_content(store, params_hash)
    record, paper = paper_window(store, strategy_id, now_ts=now_ts)
    if record.closed_trades > 0 and record.losses_lamports == 0:
        raise StageRefused("paper record has no losing closes: profit factor undefined")
    decision = f"{current.value} to {target.value}"
    if target is Stage.LIVE_ELIGIBLE:
        passed, reason = evaluate_paper_record(record, thresholds)
        if not passed:
            raise StageRefused(f"paper record refused: {reason}")
        decision = f"{decision}; paper record: {reason}"
    verdict = evaluate_candidate(
        params,
        bounds=bounds,
        search=search,
        run_id=run_id,
        store=store,
        backtest=backtest,
        paper=paper,
    )
    if not verdict.promotion_eligible:
        raise StageRefused(f"gate refused the candidate: {verdict.reason}: {verdict.detail}")
    decision = f"{decision}; gate {verdict.reason}"
    return append_stage(
        store,
        strategy_id,
        from_stage=current,
        to_stage=target,
        decision=decision,
        by=by,
        params_hash=params_hash,
        paper_window_start=record.window_start,
        evidence_hash=_evidence_hash(verdict, params_hash),
        ts_utc=ts_utc,
        source=source,
        correlation_id=correlation_id,
    )
