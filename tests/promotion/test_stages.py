"""PRM-01 (criterion 6): stage changes are ledger rows with a decision log.

Stages move BACKTEST -> PAPER -> LIVE_ELIGIBLE on recorded evidence, one step per row. The stage is folded from the rows, so a fresh ledger handle reads the same stage. Forward moves run the one gate on eligible evidence; a step to LIVE_ELIGIBLE also needs a paper record that meets the thresholds. Each refusal class (ineligible evidence, below-threshold evidence) stays put, and a refused step writes nothing. LIVE is derived and never stored, and every transition lands in the decision log. All evidence is fabricated records; no backtest run, no network.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest
from promotion_support import (
    HUMAN,
    NOW,
    OPENED_AT,
    STRATEGY,
    activate,
    advance,
    paper_history,
    param_set,
)

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.promotion import Stage, StageRefused, current_stage
from pumpgrok.promotion.evaluator import EvidenceView, PromotionEvaluator
from pumpgrok.promotion.stages import (
    Stage,
    StageRow,
    Transition,
    append_stage_row,
    append_transition,
    decision_log,
    read_stage_row,
)
from pumpgrok.promotion.stages import stage_rows
from pumpgrok.promotion.thresholds import PromotionThresholds
from pumpgrok.replay.clock import FixtureClock, format_ts_utc

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
STRATEGY = "momentum_breakout"


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", "10000000000")
    store.set_meta("source", "paper")
    return store


def _evaluator() -> PromotionEvaluator:
    return PromotionEvaluator(
        PromotionThresholds(
            min_paper_days=14,
            min_closed_trades=50,
            min_profit_factor=Decimal("1.20"),
            max_drawdown_fraction=Decimal("0.15"),
        )
    )


def _evidence(**overrides: object) -> EvidenceView:
    fields: dict[str, object] = {
        "strategy_id": STRATEGY,
        "eligible": True,
        "paper_days": 14,
        "closed_trades": 50,
        "profit_factor": Decimal("1.25"),
        "drawdown_fraction": Decimal("0.10"),
        "param_hash": "a" * 64,
        "version_id": "v1",
        "evidence_run_id": "RUN-1",
        "event_id": "evt-1",
        "metrics": {"profit_factor": "1.25"},
    }
    fields.update(overrides)
    return EvidenceView(**fields)  # type: ignore[arg-type]


def _promote(
    store: LedgerStore, clock: FixtureClock, evaluator: PromotionEvaluator, evidence: EvidenceView
) -> StageRow:
    row = read_stage_row(store, STRATEGY)
    next_stage = evaluator.next_stage(row.stage if row else None, evidence)
    new_row = StageRow(
        strategy_id=STRATEGY,
        stage=next_stage,
        version_id=evidence.version_id,
        param_hash=evidence.param_hash,
        evidence_run_id=evidence.evidence_run_id,
        metrics=evidence.metrics,
    )
    ts = format_ts_utc(clock.now())
    append_stage_row(store, new_row, by="gate:promotion", ts_utc=ts)
    append_transition(
        store,
        Transition(
            strategy_id=STRATEGY,
            previous_stage=row.stage if row else None,
            next_stage=next_stage,
            evidence_id=evidence.evidence_run_id,
            event_id=evidence.event_id,
        ),
        by="gate:promotion",
        ts_utc=ts,
    )
    clock.jump(60.0)  # distinct idempotency keys per promotion
    return new_row


def test_stages_move_forward_on_eligible_evidence(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    evaluator = _evaluator()
    first = _promote(store, clock, evaluator, _evidence())
    assert first.stage is Stage.PAPER
    second = _promote(store, clock, evaluator, _evidence(event_id="evt-2"))
    assert second.stage is Stage.LIVE_ELIGIBLE
    row = read_stage_row(store, STRATEGY)
    assert row is not None
    assert row.stage is Stage.LIVE_ELIGIBLE
    assert row.param_hash == "a" * 64
    assert row.evidence_run_id == "RUN-1"
    assert row.metrics == {"profit_factor": "1.25"}


def test_live_is_derived_and_never_stored() -> None:
    assert "LIVE" not in [stage.value for stage in Stage]


def test_ineligible_evidence_never_moves_a_stage(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    evaluator = _evaluator()
    row = _promote(store, clock, evaluator, _evidence(eligible=False))
    assert row.stage is Stage.BACKTEST
    assert (
        read_stage_row(store, STRATEGY) is None
        or read_stage_row(store, STRATEGY).stage is Stage.BACKTEST
    )


def test_below_threshold_evidence_never_moves_a_stage(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    evaluator = _evaluator()
    row = _promote(store, clock, evaluator, _evidence(closed_trades=49))
    assert row.stage is Stage.BACKTEST
    row = _promote(store, clock, evaluator, _evidence(profit_factor=Decimal("1.10")))
    assert row.stage is Stage.BACKTEST


def test_every_transition_lands_in_the_decision_log(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    evaluator = _evaluator()
    _promote(store, clock, evaluator, _evidence())
    _promote(store, clock, evaluator, _evidence(event_id="evt-2"))
    log = decision_log(store, STRATEGY)
    assert [t.next_stage for t in log] == [Stage.PAPER, Stage.LIVE_ELIGIBLE]
    assert log[0].previous_stage is None
    assert log[1].previous_stage is Stage.PAPER
    assert log[0].evidence_id == "RUN-1"
    assert log[1].event_id == "evt-2"


def test_no_evidence_means_backtest(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert read_stage_row(store, STRATEGY) is None


def test_backtest_to_paper_writes_one_row_with_decision_log(store: LedgerStore) -> None:
    params = activate(store)
    paper_history(store, wins=1, losses=1)
    advance(store, params)

    rows = stage_rows(store, STRATEGY)
    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert payload["from_stage"] == "BACKTEST"
    assert payload["to_stage"] == "PAPER"
    assert "BACKTEST to PAPER" in payload["decision"]
    assert "gate pass" in payload["decision"]
    assert payload["by"] == HUMAN
    assert payload["params_hash"] == params.content_hash
    assert len(payload["evidence_hash"]) == 64
    assert current_stage(store, STRATEGY) is Stage.PAPER


def test_gate_refusal_writes_nothing(store: LedgerStore) -> None:
    params = activate(store, min_unique_buyers=5000)
    paper_history(store, wins=1, losses=1)
    with pytest.raises(StageRefused, match="gate refused the candidate: out_of_bounds"):
        advance(store, params)
    assert stage_rows(store, STRATEGY) == []
    assert current_stage(store, STRATEGY) is Stage.BACKTEST


def test_paper_step_needs_a_paper_fill(store: LedgerStore) -> None:
    params = activate(store)
    with pytest.raises(StageRefused, match="no paper fill"):
        advance(store, params)
    assert stage_rows(store, STRATEGY) == []


def test_live_eligible_after_paper_record_meets_thresholds(store: LedgerStore) -> None:
    params = activate(store)
    paper_history(store, wins=30, losses=20)
    advance(store, params)

    row = advance(store, params)

    assert current_stage(store, STRATEGY) is Stage.LIVE_ELIGIBLE
    assert row["payload"]["to_stage"] == "LIVE_ELIGIBLE"
    assert row["payload"]["paper_window_start"] == OPENED_AT
    assert "paper record meets every threshold" in row["payload"]["decision"]
    assert len(stage_rows(store, STRATEGY)) == 2


def test_thin_paper_record_is_refused_with_nothing_written(store: LedgerStore) -> None:
    params = activate(store)
    paper_history(store, wins=5, losses=3)
    advance(store, params)

    with pytest.raises(StageRefused, match="closed trades"):
        advance(store, params)
    assert len(stage_rows(store, STRATEGY)) == 1
    assert current_stage(store, STRATEGY) is Stage.PAPER


def test_nothing_above_live_eligible(store: LedgerStore) -> None:
    params = activate(store)
    paper_history(store, wins=30, losses=20)
    advance(store, params)
    advance(store, params)

    with pytest.raises(StageRefused, match="nothing above it"):
        advance(store, params)
    assert len(stage_rows(store, STRATEGY)) == 2


def test_stage_is_folded_from_rows_on_a_fresh_handle(store: LedgerStore, ledger_path: str) -> None:
    params = activate(store)
    paper_history(store, wins=1, losses=1)
    advance(store, params, now_ts=NOW)

    other = LedgerStore(ledger_path)
    try:
        assert current_stage(other, STRATEGY) is Stage.PAPER
        assert param_set().content_hash == params.content_hash
    finally:
        other.close()
