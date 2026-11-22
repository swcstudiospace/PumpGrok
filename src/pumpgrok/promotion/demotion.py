"""Automatic demotion and one-operation rollback (PRM-04).

A parameter-hash or evidence-hash change resets the strategy stage row
to BACKTEST, appending the demotion to the decision log with the old
and new hashes. Demotion triggers (threshold evidence no longer met,
kill row present, halt present) evaluate in the same pure function, so a
demotion needs no operator action. ``demote_one_stage`` backs the
``pumpgrok promotion demote --strategy ID`` verb: one command rolls the
named strategy back exactly one stage, writes the ledger rows and exits
0. History is never deleted; the decision log keeps both directions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pumpgrok.promotion.stages import (
    Stage,
    StageRow,
    Transition,
    append_stage_row,
    append_transition,
    read_stage_row,
)

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore

__all__ = [
    "DemotionState",
    "detect_demotion",
    "demote_one_stage",
    "reset_on_hash_change",
]

_BACK_ONE: dict[Stage, Stage] = {
    Stage.LIVE_ELIGIBLE: Stage.PAPER,
    Stage.PAPER: Stage.BACKTEST,
    Stage.BACKTEST: Stage.BACKTEST,
}


class DemotionState:
    """Demotion triggers evaluated at promotion time."""

    def __init__(self, *, evidence_meets_thresholds: bool, kill_row_present: bool, halt_present: bool) -> None:
        self.evidence_meets_thresholds = evidence_meets_thresholds
        self.kill_row_present = kill_row_present
        self.halt_present = halt_present


def detect_demotion(current: Stage, state: DemotionState) -> Stage | None:
    """Demoted stage for lost evidence, a kill row, or a halt; else None."""
    if not state.evidence_meets_thresholds or state.kill_row_present or state.halt_present:
        return _BACK_ONE[current]
    return None


def demote_one_stage(
    store: LedgerStore,
    strategy_id: str,
    *,
    by: str,
    ts_utc: str,
    source: str = "paper",
    correlation_id: str = "desk",
) -> StageRow | None:
    """Roll one strategy back exactly one stage; None when unknown."""
    row = read_stage_row(store, strategy_id)
    if row is None:
        return None
    back = _BACK_ONE[row.stage]
    if back == row.stage:
        return row
    demoted = StageRow(
        strategy_id=strategy_id,
        stage=back,
        version_id=row.version_id,
        param_hash=row.param_hash,
        evidence_run_id=row.evidence_run_id,
        metrics=row.metrics,
    )
    append_stage_row(store, demoted, by=by, ts_utc=ts_utc, source=source, correlation_id=correlation_id)
    append_transition(
        store,
        Transition(
            strategy_id=strategy_id,
            previous_stage=row.stage,
            next_stage=back,
            evidence_id=row.evidence_run_id,
            event_id="promotion-demote",
        ),
        by=by,
        ts_utc=ts_utc,
        source=source,
        correlation_id=correlation_id,
    )
    return demoted


def reset_on_hash_change(
    store: LedgerStore,
    strategy_id: str,
    new_param_hash: str,
    *,
    by: str,
    ts_utc: str,
    source: str = "paper",
    correlation_id: str = "desk",
) -> StageRow | None:
    """Reset to BACKTEST when the parameter hash changed; else the row."""
    row = read_stage_row(store, strategy_id)
    if row is None:
        return None
    if row.param_hash == new_param_hash:
        return row
    reset = StageRow(
        strategy_id=strategy_id,
        stage=Stage.BACKTEST,
        version_id=row.version_id,
        param_hash=new_param_hash,
        evidence_run_id=row.evidence_run_id,
        metrics=row.metrics,
    )
    append_stage_row(store, reset, by=by, ts_utc=ts_utc, source=source, correlation_id=correlation_id)
    append_transition(
        store,
        Transition(
            strategy_id=strategy_id,
            previous_stage=row.stage,
            next_stage=Stage.BACKTEST,
            evidence_id=f"param:{row.param_hash}->{new_param_hash}",
            event_id="promotion-hash-change",
        ),
        by=by,
        ts_utc=ts_utc,
        source=source,
        correlation_id=correlation_id,
    )
    return reset
