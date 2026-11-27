"""PRM-04: hash change resets to BACKTEST, demotion is automatic, one
operation rolls back (criterion 7).

Demotion matrix: hash change, evidence loss, kill present, halt present.
A change of the active parameter set resets every stage granted under the old set to BACKTEST,
in one ledger row. demote() moves a strategy down one stage in one row and refuses at BACKTEST.
The CLI verb ``pumpgrok promotion demote --strategy ID`` rolls exactly one stage and exits 0.
History is never deleted.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest
from promotion_support import HUMAN, LATER_TS, STRATEGY, activate, advance, paper_history

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.promotion import StageRefused, current_stage
from pumpgrok.promotion.demote import RESET_BY, demote
from pumpgrok.promotion.demote import reset_on_hash_change as demote_reset_on_hash_change
from pumpgrok.promotion.demotion import (
    DemotionState,
    demote_one_stage,
    detect_demotion,
)
from pumpgrok.promotion.demotion import reset_on_hash_change as demotion_reset_on_hash_change
from pumpgrok.promotion.stages import (
    Stage,
    StageRow,
    append_stage_row,
    decision_log,
    read_stage_row,
    stage_rows,
)
from pumpgrok.replay.clock import FixtureClock, format_ts_utc

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", "10000000000")
    store.set_meta("source", "paper")
    return store


def _seed(store: LedgerStore, clock: FixtureClock, stage: Stage) -> None:
    append_stage_row(
        store,
        StageRow(
            strategy_id=STRATEGY,
            stage=stage,
            version_id="v1",
            param_hash="a" * 64,
            evidence_run_id="RUN-1",
            metrics={"k": 1},
        ),
        by="gate:promotion",
        ts_utc=format_ts_utc(clock.now()),
    )


def test_hash_change_resets_to_backtest(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _seed(store, clock, Stage.PAPER)
    reset = demotion_reset_on_hash_change(
        store, STRATEGY, "b" * 64, by="gate:promotion", ts_utc=format_ts_utc(clock.now())
    )
    assert reset is not None
    assert reset.stage is Stage.BACKTEST
    assert reset.param_hash == "b" * 64
    log = decision_log(store, STRATEGY)
    assert log and log[-1].next_stage is Stage.BACKTEST
    assert "a" * 64 in log[-1].evidence_id
    assert "b" * 64 in log[-1].evidence_id


def test_same_hash_does_not_reset(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _seed(store, clock, Stage.PAPER)
    row = demotion_reset_on_hash_change(
        store, STRATEGY, "a" * 64, by="gate:promotion", ts_utc=format_ts_utc(clock.now())
    )
    assert row is not None
    assert row.stage is Stage.PAPER


def test_detect_demotion_triggers() -> None:
    assert (
        detect_demotion(
            Stage.PAPER,
            DemotionState(
                evidence_meets_thresholds=False, kill_row_present=False, halt_present=False
            ),
        )
        is Stage.BACKTEST
    )
    assert (
        detect_demotion(
            Stage.LIVE_ELIGIBLE,
            DemotionState(
                evidence_meets_thresholds=True, kill_row_present=True, halt_present=False
            ),
        )
        is Stage.PAPER
    )
    assert (
        detect_demotion(
            Stage.LIVE_ELIGIBLE,
            DemotionState(
                evidence_meets_thresholds=True, kill_row_present=False, halt_present=True
            ),
        )
        is Stage.PAPER
    )
    assert (
        detect_demotion(
            Stage.PAPER,
            DemotionState(
                evidence_meets_thresholds=True, kill_row_present=False, halt_present=False
            ),
        )
        is None
    )


def test_demote_rolls_back_exactly_one_stage(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _seed(store, clock, Stage.LIVE_ELIGIBLE)
    demoted = demote_one_stage(store, STRATEGY, by="human:alice", ts_utc=format_ts_utc(clock.now()))
    assert demoted is not None
    assert demoted.stage is Stage.PAPER
    assert read_stage_row(store, STRATEGY).stage is Stage.PAPER  # type: ignore[union-attr]
    again = demote_one_stage(
        store, STRATEGY, by="human:alice", ts_utc=format_ts_utc(clock.now() + 60)
    )
    assert again is not None
    assert again.stage is Stage.BACKTEST
    log = decision_log(store, STRATEGY)
    assert [t.next_stage for t in log] == [Stage.PAPER, Stage.BACKTEST]


def test_demote_unknown_strategy_returns_none(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    assert (
        demote_one_stage(store, "nope", by="human:alice", ts_utc=format_ts_utc(clock.now())) is None
    )


def _live(store: LedgerStore):
    """Reach LIVE_ELIGIBLE under one active set; return that set."""
    params = activate(store)
    paper_history(store, wins=30, losses=20)
    advance(store, params)
    advance(store, params)
    assert current_stage(store, STRATEGY) is Stage.LIVE_ELIGIBLE
    return params


def test_hash_change_resets_to_backtest_in_one_row(store: LedgerStore) -> None:
    _live(store)
    before = len(stage_rows(store, STRATEGY))

    activate(store, min_unique_buyers=6, ts_utc=LATER_TS)
    row = demote_reset_on_hash_change(store, STRATEGY, ts_utc=LATER_TS)

    assert row is not None
    assert row["payload"]["to_stage"] == "BACKTEST"
    assert row["payload"]["by"] == RESET_BY
    assert "parameter hash changed" in row["payload"]["decision"]
    assert len(stage_rows(store, STRATEGY)) == before + 1
    assert current_stage(store, STRATEGY) is Stage.BACKTEST


def test_unchanged_hash_does_not_reset(store: LedgerStore) -> None:
    _live(store)
    assert demote_reset_on_hash_change(store, STRATEGY, ts_utc=LATER_TS) is None
    assert current_stage(store, STRATEGY) is Stage.LIVE_ELIGIBLE


def test_reset_is_a_no_op_at_backtest(store: LedgerStore) -> None:
    activate(store)
    assert demote_reset_on_hash_change(store, STRATEGY, ts_utc=LATER_TS) is None
    assert stage_rows(store, STRATEGY) == []


def test_candidate_after_reset_is_refused_until_it_is_active(store: LedgerStore) -> None:
    old = _live(store)
    new = activate(store, min_unique_buyers=6, ts_utc=LATER_TS)
    demote_reset_on_hash_change(store, STRATEGY, ts_utc=LATER_TS)

    with pytest.raises(StageRefused, match="not the active parameter set"):
        advance(store, old, now_ts=LATER_TS)
    assert new.content_hash != old.content_hash
    assert current_stage(store, STRATEGY) is Stage.BACKTEST


def test_demote_rolls_back_one_stage_in_one_row(store: LedgerStore) -> None:
    _live(store)
    before = len(stage_rows(store, STRATEGY))

    row = demote(store, STRATEGY, by=HUMAN, reason="manual review", ts_utc=LATER_TS)

    assert row["payload"]["from_stage"] == "LIVE_ELIGIBLE"
    assert row["payload"]["to_stage"] == "PAPER"
    assert row["payload"]["by"] == HUMAN
    assert len(stage_rows(store, STRATEGY)) == before + 1
    assert current_stage(store, STRATEGY) is Stage.PAPER


def test_demote_twice_reaches_backtest_then_refuses(store: LedgerStore) -> None:
    _live(store)
    demote(store, STRATEGY, by=HUMAN, reason="first", ts_utc=LATER_TS)
    demote(store, STRATEGY, by=HUMAN, reason="second", ts_utc=LATER_TS)
    assert current_stage(store, STRATEGY) is Stage.BACKTEST

    with pytest.raises(StageRefused, match="nothing to demote"):
        demote(store, STRATEGY, by=HUMAN, reason="third", ts_utc=LATER_TS)


def test_demote_refuses_without_a_reason(store: LedgerStore) -> None:
    _live(store)
    with pytest.raises(StageRefused, match="needs a reason"):
        demote(store, STRATEGY, by=HUMAN, reason="   ", ts_utc=LATER_TS)
    assert current_stage(store, STRATEGY) is Stage.LIVE_ELIGIBLE
