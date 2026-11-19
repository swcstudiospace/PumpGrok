"""Event-triggered promotion evaluator (PRM-05, criterion 8).

PromotionEvaluator.handle takes one ledger row. A FillRecorded or PositionClosed row can move a
strategy's paper record, so it is the trigger; any other row is ignored. For a trigger, the
handler attributes the row to a strategy through its ticket, then runs the existing stage step
once (advance_stage: the gate and the thresholds of config/promotion_thresholds.toml). A
refused step writes nothing. At most one PromotionStageSet row is written per event.

The gate's inputs (the holdout search result, the backtest report, the bounds and the active
parameter set) come from an injected evidence source. The handler runs no search, starts no
timer, and makes no model call; the caller decides when each event is handled.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pumpgrok.ledger.active_set import is_writer
from pumpgrok.ledger.ticket_refs import load_refs
from pumpgrok.promotion.stages import Stage, StageRefused, advance_stage, current_stage

if TYPE_CHECKING:
    from pumpgrok.backtest.harness import HarnessResult
    from pumpgrok.backtest.metrics import MetricsReport
    from pumpgrok.ledger.store import LedgerStore
    from pumpgrok.promotion.thresholds import PromotionThresholds
    from pumpgrok.upgrade.bounds import Bounds
    from pumpgrok.upgrade.params import ParamSet

__all__ = [
    "EVALUATOR_BY",
    "TRIGGER_TYPES",
    "EvidenceSource",
    "PromotionEvaluator",
    "PromotionEvidence",
]

#: Ledger row types that can move a strategy's paper record.
TRIGGER_TYPES: frozenset[str] = frozenset({"FillRecorded", "PositionClosed"})

#: Writer on every stage row the evaluator appends. It is gate-written, so is_writer accepts it.
EVALUATOR_BY = "gate:promotion-evaluator"


@dataclass(frozen=True)
class PromotionEvidence:
    """The gate's inputs for one strategy's next stage step, from its holdout run."""

    params: ParamSet
    bounds: Bounds
    search: HarnessResult
    run_id: str
    backtest: MetricsReport


#: Strategy id to its evidence, or None when no holdout evidence exists for it yet.
EvidenceSource = Callable[[str], PromotionEvidence | None]


def _open_ticket(store: LedgerStore, mint: str, *, before_seq: int) -> str:
    """The ticket open on mint as of the row at before_seq; empty when none is open."""
    open_ticket = ""
    for event in store.read(types=["PositionOpened", "PositionClosed"], limit=None):
        if event["seq"] >= before_seq:
            break
        payload = event["payload"]
        if payload.get("mint") != mint:
            continue
        if event["type"] == "PositionOpened":
            open_ticket = str(payload.get("ticket_id", "") or "")
        else:
            open_ticket = ""
    return open_ticket


def _strategy_of(store: LedgerStore, row: Mapping[str, Any]) -> str | None:
    """The strategy the row's ticket is attributed to, or None for an unattributed row.

    A row that names its ticket uses it. A row that names only its mint takes the ticket open on
    that mint just before the row, so a close is attributed to the position it closes.
    """
    payload = row["payload"]
    ticket = str(payload.get("ticket_id", "") or "")
    mint = str(payload.get("mint", "") or "")
    if not ticket and mint:
        ticket = _open_ticket(store, mint, before_seq=int(row["seq"]))
    if not ticket:
        return None
    return load_refs(store).get(ticket)


class PromotionEvaluator:
    """Runs the gate and thresholds for one trigger row's strategy; writes at most one row.

    Rows are ledger rows as LedgerStore.read returns them (they carry seq). The caller routes each
    appended row whose type is in TRIGGER_TYPES, or every row; other rows return None.
    """

    def __init__(
        self,
        store: LedgerStore,
        *,
        evidence: EvidenceSource,
        thresholds: PromotionThresholds,
        by: str = EVALUATOR_BY,
        source: str = "paper",
        correlation_id: str = "promotion-evaluator",
    ) -> None:
        if not is_writer(by):
            raise ValueError(
                f"promotion evaluator writer must be a human: or gate: writer, got {by!r}"
            )
        self._store = store
        self._evidence = evidence
        self._thresholds = thresholds
        self._by = by
        self._source = source
        self._correlation_id = correlation_id

    def handle(self, row: Mapping[str, Any]) -> dict[str, Any] | None:
        """Evaluate one ledger row; return the stage row written, or None when nothing moved."""
        if row["type"] not in TRIGGER_TYPES:
            return None
        strategy_id = _strategy_of(self._store, row)
        if strategy_id is None:
            return None
        if current_stage(self._store, strategy_id) is Stage.LIVE_ELIGIBLE:
            return None
        evidence = self._evidence(strategy_id)
        if evidence is None:
            return None
        ts_utc = str(row["ts_utc"])
        try:
            return advance_stage(
                self._store,
                strategy_id,
                params=evidence.params,
                bounds=evidence.bounds,
                search=evidence.search,
                run_id=evidence.run_id,
                backtest=evidence.backtest,
                by=self._by,
                now_ts=ts_utc,
                thresholds=self._thresholds,
                ts_utc=ts_utc,
                source=self._source,
                correlation_id=self._correlation_id,
            )
        except StageRefused:
            return None
