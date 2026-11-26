"""PRM-06 (criterion 9): only writers write stages, and stored content is verified first.

Only is_writer callers write: a non-writer caller raises instead of writing; a writer (human or gate) writes through the same helpers. A stage change or demotion needs a human: or gate: caller, and the parameter set's stored content must verify before any row is written; a refused call appends nothing. Stored stage content is read back from the ledger and verified (hash-chain intact) before use.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from promotion_support import CORR, HUMAN, NOW, STRATEGY, activate, advance, paper_history

from pumpgrok.ledger.active_set import is_writer, verify_stored_content
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.promotion import Stage, StageRefused, current_stage
from pumpgrok.promotion import stages as stages_module
from pumpgrok.promotion.demote import demote
from pumpgrok.promotion.stages import (
    Stage,
    StageRow,
    Transition,
    append_stage_row,
    append_transition,
    read_stage_row,
)
from pumpgrok.promotion.stages import stage_rows
from pumpgrok.replay.clock import FixtureClock, format_ts_utc

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
STRATEGY = "momentum_breakout"


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", "10000000000")
    store.set_meta("source", "paper")
    return store


def test_is_writer_vocabulary() -> None:
    assert is_writer("human:alice") is True
    assert is_writer("gate:promotion") is True
    assert is_writer("risk_engine") is False
    assert is_writer("") is False
    assert is_writer(None) is False


def test_non_writer_stage_write_raises(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        append_stage_row(
            store,
            StageRow(strategy_id=STRATEGY, stage=Stage.PAPER),
            by="risk_engine",
            ts_utc=format_ts_utc(clock.now()),
        )
    assert read_stage_row(store, STRATEGY) is None


def test_non_writer_transition_write_raises(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        append_transition(
            store,
            Transition(
                strategy_id=STRATEGY,
                previous_stage=None,
                next_stage=Stage.PAPER,
                evidence_id="RUN-1",
                event_id="evt-1",
            ),
            by="bot-04-sniper",
            ts_utc=format_ts_utc(clock.now()),
        )


def test_writer_write_is_verified_on_read(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    row = StageRow(
        strategy_id=STRATEGY,
        stage=Stage.PAPER,
        version_id="v1",
        param_hash="a" * 64,
        evidence_run_id="RUN-1",
        metrics={"profit_factor": "1.25"},
    )
    append_stage_row(store, row, by="gate:promotion", ts_utc=format_ts_utc(clock.now()))
    store.verify()  # hash chain intact
    assert read_stage_row(store, STRATEGY) == row
    assert store.count() >= 1


@pytest.mark.parametrize(
    ("by", "accepted"),
    [
        ("human:alice", True),
        ("gate:promotion-check", True),
        ("bot-02-risk", False),
        ("seat:bot-02-risk", False),
        ("", False),
        (None, False),
    ],
)
def test_is_writer_accepts_only_human_and_gate(by: object, accepted: bool) -> None:
    assert is_writer(by) is accepted


@pytest.mark.parametrize("by", ["bot-02-risk", "", None])
def test_non_writer_cannot_advance_a_stage(store: LedgerStore, by: object) -> None:
    params = activate(store)
    paper_history(store, wins=1, losses=1)
    with pytest.raises(StageRefused, match="human: or gate: writer"):
        advance(store, params, by=by)  # type: ignore[arg-type]
    assert stage_rows(store, STRATEGY) == []


def test_non_writer_cannot_demote(store: LedgerStore) -> None:
    params = activate(store)
    paper_history(store, wins=1, losses=1)
    advance(store, params)
    with pytest.raises(StageRefused, match="human: or gate: writer"):
        demote(store, STRATEGY, by="bot-02-risk", reason="x", ts_utc=NOW)
    assert current_stage(store, STRATEGY) is Stage.PAPER


def test_stored_content_is_verified_before_the_row_is_written(
    store: LedgerStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    params = activate(store)
    paper_history(store, wins=1, losses=1)

    def _tampered(_store: LedgerStore, content_hash: str) -> None:
        raise ValueError(f"active param set {content_hash} content does not match its hash")

    monkeypatch.setattr(stages_module, "verify_stored_content", _tampered)
    with pytest.raises(ValueError, match="does not match its hash"):
        advance(store, params)
    assert stage_rows(store, STRATEGY) == []


def test_recorded_content_verifies_and_advances(store: LedgerStore) -> None:
    params = activate(store)
    paper_history(store, wins=1, losses=1)
    verify_stored_content(store, params.content_hash)

    row = advance(store, params, by="gate:promotion-check")

    assert row["payload"]["by"] == "gate:promotion-check"
    assert current_stage(store, STRATEGY) is Stage.PAPER


def test_forged_stage_row_from_a_seat_does_not_fold(store: LedgerStore) -> None:
    """A PromotionStageSet row whose by is a seat never changes the folded stage."""
    store.append_batch(
        [
            {
                "ts_utc": NOW,
                "source": "paper",
                "correlation_id": CORR,
                "idempotency_key": "forged-stage-row",
                "type": "PromotionStageSet",
                "payload": {
                    "source": "paper",
                    "strategy_id": STRATEGY,
                    "from_stage": "BACKTEST",
                    "to_stage": "LIVE_ELIGIBLE",
                    "decision": "forged by a seat",
                    "by": "bot-02-risk",
                    "params_hash": "",
                    "paper_window_start": "",
                    "evidence_hash": "",
                },
            }
        ]
    )
    assert current_stage(store, STRATEGY) is Stage.BACKTEST

    params = activate(store)
    paper_history(store, wins=1, losses=1)
    row = advance(store, params)

    assert row["payload"]["from_stage"] == "BACKTEST"
    assert row["payload"]["to_stage"] == "PAPER"
    assert HUMAN.startswith("human:")
