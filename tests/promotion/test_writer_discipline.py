"""PRM-06: only is_writer callers write and stored content is verified.

A non-writer caller raises instead of writing; a writer (human or gate)
writes through the same helpers. Stored stage content is read back from
the ledger and verified (hash-chain intact) before use.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.ledger.active_set import is_writer
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.promotion.stages import (
    Stage,
    StageRow,
    Transition,
    append_stage_row,
    append_transition,
    read_stage_row,
)
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
