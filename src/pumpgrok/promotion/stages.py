"""Promotion stage machine on ledger rows (PRM-01, PRM-04, PRM-06).

Stages BACKTEST, PAPER and LIVE_ELIGIBLE are ledger rows (JournalNote
verdicts), one per strategy, each carrying the strategy version id, the
parameter-set hash, the evidence run id and the deciding metrics
snapshot. LIVE is derived from LIVE_ELIGIBLE plus the arm record and is
never stored (V4-11). Every transition appends to a decision log row
with the evidence id, the triggering event id and the previous stage.

Only ``is_writer`` callers write, and stored content is verified before
use; a non-writer caller raises instead of writing (PRM-06).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pumpgrok.ledger.active_set import is_writer

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore
__all__ = [
    "Stage",
    "StageRow",
    "append_stage_row",
    "append_transition",
    "decision_log",
    "read_stage_row",
]

STAGE_PREFIX = "PROMOTION stage="
TRANSITION_PREFIX = "PROMOTION transition "


class Stage(StrEnum):
    """Stored stages. LIVE is derived, never stored."""

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
