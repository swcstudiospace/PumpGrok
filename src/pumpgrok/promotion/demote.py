"""Parameter-hash reset and one-operation demotion (PRM-04).

A parameter hash change resets a strategy that holds a stage to BACKTEST. The reset compares
the hash of the stage's last row with the active parameter set. demote() rolls one strategy
down one stage in one PromotionStageSet row. Both paths write through append_stage, so the
ledger keeps the full history.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pumpgrok.ledger.active_set import read_active_set, verify_stored_content
from pumpgrok.promotion.stages import (
    Stage,
    StageRefused,
    append_stage,
    current_stage,
    last_stage_row,
    lower_stage,
    require_writer,
)

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore

__all__ = ["RESET_BY", "demote", "reset_on_hash_change"]

#: Writer recorded on the automatic reset row. It is gate-written, so is_writer accepts it.
RESET_BY = "gate:parameter-hash-reset"


def reset_on_hash_change(
    store: LedgerStore,
    strategy_id: str,
    *,
    ts_utc: str,
    source: str = "paper",
    correlation_id: str = "promotion",
) -> dict[str, Any] | None:
    """Reset to BACKTEST when the active set differs from the one the stage was granted under.

    Returns the reset row, or None when the strategy is already at BACKTEST or its granted hash
    still matches the active set.
    """
    stage = current_stage(store, strategy_id)
    if stage is Stage.BACKTEST:
        return None
    last = last_stage_row(store, strategy_id)
    granted = str(last["payload"].get("params_hash", "")) if last is not None else ""
    active = read_active_set(store) or ""
    if granted == active:
        return None
    if active:
        verify_stored_content(store, active)
    return append_stage(
        store,
        strategy_id,
        from_stage=stage,
        to_stage=Stage.BACKTEST,
        decision=(
            f"parameter hash changed from {granted or 'none'} to {active or 'none'}: "
            "reset to BACKTEST"
        ),
        by=RESET_BY,
        params_hash=active,
        paper_window_start="",
        evidence_hash="",
        ts_utc=ts_utc,
        source=source,
        correlation_id=correlation_id,
    )


def demote(
    store: LedgerStore,
    strategy_id: str,
    *,
    by: str,
    reason: str,
    ts_utc: str,
    source: str = "paper",
    correlation_id: str = "promotion",
) -> dict[str, Any]:
    """Roll one strategy down one stage in one row; return the row written.

    Refused, with nothing written, unless the writer is human: or gate:, the reason is named, and
    the strategy is above BACKTEST.
    """
    if not strategy_id:
        raise StageRefused("a demotion needs a strategy id")
    require_writer(by)
    if not reason.strip():
        raise StageRefused("a demotion needs a reason")
    stage = current_stage(store, strategy_id)
    lower = lower_stage(stage)
    if lower is None:
        raise StageRefused(f"strategy {strategy_id} is at BACKTEST: nothing to demote")
    last = last_stage_row(store, strategy_id)
    granted = str(last["payload"].get("params_hash", "")) if last is not None else ""
    if granted:
        verify_stored_content(store, granted)
    # TODO(owner): demotion triggers beyond the parameter-hash reset (index Finding 7) are not
    # decided here. Each one appends its own row through append_stage at this call site.
    return append_stage(
        store,
        strategy_id,
        from_stage=stage,
        to_stage=lower,
        decision=f"demoted by {by}: {reason}",
        by=by,
        params_hash=granted,
        paper_window_start="",
        evidence_hash="",
        ts_utc=ts_utc,
        source=source,
        correlation_id=correlation_id,
    )
