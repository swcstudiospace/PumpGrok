"""PRM-01 (criterion 6): stage changes are ledger rows with a decision log.

BACKTEST to PAPER to LIVE_ELIGIBLE, one step per row. The stage is folded from the rows, so a
fresh ledger handle reads the same stage. Every step runs the one gate; a step to LIVE_ELIGIBLE
also needs a paper record that meets the thresholds. A refused step writes nothing.
"""

from __future__ import annotations

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
from pumpgrok.promotion.stages import stage_rows


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
