"""PRM-04: hash change resets to BACKTEST, demotion is automatic, one operation rolls back.

Demotion matrix: hash change, evidence loss, kill present, halt present.
The CLI verb ``pumpgrok promotion demote --strategy ID`` rolls exactly
one stage and exits 0. History is never deleted.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.promotion.demotion import (
    DemotionState,
    demote_one_stage,
    detect_demotion,
    reset_on_hash_change,
)
from pumpgrok.promotion.stages import Stage, StageRow, append_stage_row, decision_log, read_stage_row
from pumpgrok.replay.clock import FixtureClock, format_ts_utc

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
STRATEGY = "momentum_breakout"


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
    _seed(store, clock, Stage.LIVE_ELIGIBLE)
    reset = reset_on_hash_change(store, STRATEGY, "b" * 64, by="gate:promotion", ts_utc=format_ts_utc(clock.now()))
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
    row = reset_on_hash_change(store, STRATEGY, "a" * 64, by="gate:promotion", ts_utc=format_ts_utc(clock.now()))
    assert row is not None
    assert row.stage is Stage.PAPER


def test_detect_demotion_triggers() -> None:
    assert detect_demotion(Stage.PAPER, DemotionState(evidence_meets_thresholds=False, kill_row_present=False, halt_present=False)) is Stage.BACKTEST
    assert detect_demotion(Stage.LIVE_ELIGIBLE, DemotionState(evidence_meets_thresholds=True, kill_row_present=True, halt_present=False)) is Stage.PAPER
    assert detect_demotion(Stage.LIVE_ELIGIBLE, DemotionState(evidence_meets_thresholds=True, kill_row_present=False, halt_present=True)) is Stage.PAPER
    assert detect_demotion(Stage.PAPER, DemotionState(evidence_meets_thresholds=True, kill_row_present=False, halt_present=False)) is None


def test_demote_rolls_back_exactly_one_stage(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _seed(store, clock, Stage.LIVE_ELIGIBLE)
    demoted = demote_one_stage(store, STRATEGY, by="human:alice", ts_utc=format_ts_utc(clock.now()))
    assert demoted is not None
    assert demoted.stage is Stage.PAPER
    assert read_stage_row(store, STRATEGY).stage is Stage.PAPER  # type: ignore[union-attr]
    again = demote_one_stage(store, STRATEGY, by="human:alice", ts_utc=format_ts_utc(clock.now() + 60))
    assert again is not None
    assert again.stage is Stage.BACKTEST
    log = decision_log(store, STRATEGY)
    assert [t.next_stage for t in log] == [Stage.PAPER, Stage.BACKTEST]


def test_demote_unknown_strategy_returns_none(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    assert demote_one_stage(store, "nope", by="human:alice", ts_utc=format_ts_utc(clock.now())) is None
