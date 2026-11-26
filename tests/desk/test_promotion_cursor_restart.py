"""Promotion cursor across a restart: each evidence event is handled once.

The desk saves its cursor to the store's meta table under
``promotion_cursor`` (last handled event id) and ``promotion_pending``
(in-flight event id). Before an event is handled, its id is recorded as
pending and cleared after; on restart a pending event is resumed past when
the evaluator wrote a transition after it, and handled again when it did
not. The crashes here are BaseException doubles raised from inside the
handle, so the pending mark is never cleared. Offline and deterministic:
no network, the stage rows are written by the desk under test.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.adapter import ExecutionMode
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.promotion.evaluator import EvidenceView
from pumpgrok.promotion.stages import Stage, decision_log, read_stage_row
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor import event_desk as desk_module
from pumpgrok.supervisor.event_desk import EventDesk, build_event_desk

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
STRATEGY = "momentum_breakout"


class SimulatedCrash(BaseException):
    """The desk dies inside the handle. A BaseException, so the pending mark stays."""


class _CrashBeforeStage:
    """Evaluates no stage: crashes inside the handle, before any stage row is written."""

    def next_stage(self, current: Stage | None, evidence: EvidenceView) -> Stage:
        raise SimulatedCrash("before the stage row")


def _create(path: Path) -> LedgerStore:
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", "10000000000")
    store.set_meta("source", "paper")
    return store


def _desk(store: LedgerStore, clock: FixtureClock, tmp_path: Path) -> EventDesk:
    return build_event_desk(
        mode=ExecutionMode.PAPER,
        store=store,
        clock=clock,
        place=lambda intent: None,
        sidecar_path=tmp_path / "events-sidecar.sqlite",
        params={STRATEGY: {"breakout_bps": 100}},
    )


def _evidence(event_id: str, run_id: str) -> EvidenceView:
    return EvidenceView(
        strategy_id=STRATEGY,
        eligible=True,
        paper_days=14,
        closed_trades=50,
        profit_factor=Decimal("1.25"),
        drawdown_fraction=Decimal("0.10"),
        param_hash="a" * 64,
        version_id="v1",
        evidence_run_id=run_id,
        event_id=event_id,
    )


def test_restart_resumes_after_the_saved_cursor(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    clock = FixtureClock(start=START)
    store = _create(path)
    desk = _desk(store, clock, tmp_path)
    desk.handle_evidence(_evidence("evt-1", "RUN-1"))
    clock.advance_to(START + 60.0)
    desk.handle_evidence(_evidence("evt-2", "RUN-2"))
    assert store.get_meta("promotion_cursor") == "evt-2"
    assert store.get_meta("promotion_pending") == ""
    assert [entry.event_id for entry in decision_log(store, STRATEGY)] == ["evt-1", "evt-2"]
    store.close()

    fresh = LedgerStore(str(path))
    try:
        clock.advance_to(START + 120.0)
        resumed = _desk(fresh, clock, tmp_path)
        # A redelivery of the last handled event is skipped, not re-advanced.
        skipped = resumed.handle_evidence(_evidence("evt-2", "RUN-2"))
        assert skipped.stage is Stage.LIVE_ELIGIBLE
        assert [entry.event_id for entry in decision_log(fresh, STRATEGY)] == ["evt-1", "evt-2"]
    finally:
        fresh.close()


def test_crash_after_the_stage_row_does_not_advance_the_strategy_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ledger.sqlite"
    clock = FixtureClock(start=START)
    store = _create(path)
    desk = _desk(store, clock, tmp_path)
    real_append_transition = desk_module.append_transition

    def _stage_then_crash(*args: Any, **kwargs: Any) -> None:
        real_append_transition(*args, **kwargs)
        raise SimulatedCrash("after the stage row")

    monkeypatch.setattr(desk_module, "append_transition", _stage_then_crash)
    evidence = _evidence("evt-1", "RUN-1")
    with pytest.raises(SimulatedCrash):
        desk.handle_evidence(evidence)
    assert store.get_meta("promotion_pending") == "evt-1"
    assert store.get_meta("promotion_cursor") != "evt-1"
    assert read_stage_row(store, STRATEGY) is not None
    assert read_stage_row(store, STRATEGY).stage is Stage.PAPER  # type: ignore[union-attr]
    store.close()

    fresh = LedgerStore(str(path))
    try:
        clock.advance_to(START + 60.0)
        resumed = _desk(fresh, clock, tmp_path)
        # The pending event already landed a transition: resumed past, never advanced twice.
        row = resumed.handle_evidence(evidence)
        assert row.stage is Stage.PAPER
        assert [entry.event_id for entry in decision_log(fresh, STRATEGY)] == ["evt-1"]
        assert fresh.get_meta("promotion_cursor") == "evt-1"
        assert fresh.get_meta("promotion_pending") == ""
    finally:
        fresh.close()


def test_crash_before_any_stage_row_handles_the_event_once(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    clock = FixtureClock(start=START)
    store = _create(path)
    desk = _desk(store, clock, tmp_path)
    desk.evaluator = _CrashBeforeStage()  # type: ignore[assignment]
    evidence = _evidence("evt-1", "RUN-1")
    with pytest.raises(SimulatedCrash):
        desk.handle_evidence(evidence)
    assert store.get_meta("promotion_pending") == "evt-1"
    assert read_stage_row(store, STRATEGY) is None
    store.close()

    fresh = LedgerStore(str(path))
    try:
        clock.advance_to(START + 60.0)
        resumed = _desk(fresh, clock, tmp_path)
        # No transition landed, so the pending event is handled again, once.
        row = resumed.handle_evidence(evidence)
        assert row.stage is Stage.PAPER
        assert [entry.event_id for entry in decision_log(fresh, STRATEGY)] == ["evt-1"]
        assert fresh.get_meta("promotion_cursor") == "evt-1"
        # And a further redelivery of the same event does not advance it again.
        again = resumed.handle_evidence(evidence)
        assert again.stage is Stage.PAPER
        assert [entry.event_id for entry in decision_log(fresh, STRATEGY)] == ["evt-1"]
    finally:
        fresh.close()
