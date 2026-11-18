"""Promotion feed cursor across a restart: each trigger row is handled once.

The feed saves its cursor to the store's meta table. A trigger row is recorded as pending before
it is handled and cleared after. On restart a pending row is resumed past when the evaluator wrote
a stage row after it, and handled again when it did not. The crashes here are BaseException
doubles raised from inside the handle, so the feed never clears the pending record. Offline and
deterministic: no evaluator gate runs, the stage rows are written by the doubles.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.events.event_desk import PromotionFeed
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.promotion.evaluator import EVALUATOR_BY
from pumpgrok.replay.clock import format_ts_utc

START = 1_700_000_000.0
STRATEGY = "momentum_breakout"


class SimulatedCrash(BaseException):
    """The desk dies inside the evaluator. A BaseException, so the feed never clears its record."""


class _Recorder:
    """Records the seq of each handled row and writes no stage row."""

    def __init__(self) -> None:
        self.seen: list[int] = []

    def handle(self, row: dict) -> None:
        self.seen.append(int(row["seq"]))


class _StageThenCrash:
    """Writes the stage row for the handled trigger, then crashes before the pending mark clears."""

    def __init__(self, store: LedgerStore) -> None:
        self._store = store
        self.handled: list[int] = []

    def handle(self, row: dict) -> None:
        self.handled.append(int(row["seq"]))
        self._store.append_batch([_stage_row("stage|test")])
        raise SimulatedCrash("after the stage row")


class _CrashBeforeStage:
    """Crashes inside the handle, before any stage row is written."""

    def __init__(self) -> None:
        self.handled: list[int] = []

    def handle(self, row: dict) -> None:
        self.handled.append(int(row["seq"]))
        raise SimulatedCrash("before the stage row")


def _create(path: Path) -> LedgerStore:
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", "1000000")
    store.set_meta("source", "paper")
    return store


def _close(store: LedgerStore, mint: str) -> None:
    payload = {
        "source": "paper",
        "mint": mint,
        "price_exit": "50",
        "proceeds_lamports": 500,
        "realized_pnl_lamports": -500,
        "reason": "stop_loss",
    }
    row = {
        "ts_utc": format_ts_utc(START),
        "source": "paper",
        "correlation_id": "test",
        "idempotency_key": f"close|{mint}",
        "type": "PositionClosed",
        "payload": payload,
    }
    store.append_batch([row])


def _stage_row(key: str) -> dict:
    return {
        "ts_utc": format_ts_utc(START),
        "source": "paper",
        "correlation_id": "test",
        "idempotency_key": key,
        "type": "PromotionStageSet",
        "payload": {
            "source": "paper",
            "strategy_id": STRATEGY,
            "from_stage": "BACKTEST",
            "to_stage": "PAPER",
            "decision": "BACKTEST to PAPER",
            "by": EVALUATOR_BY,
            "params_hash": "params",
            "paper_window_start": "",
            "evidence_hash": "evidence",
        },
    }


def test_restart_resumes_after_the_saved_cursor(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    store = _create(path)
    _close(store, "MintA")
    _close(store, "MintB")
    first = _Recorder()
    feed = PromotionFeed(store, first)  # type: ignore[arg-type]
    _close(store, "MintC")
    _close(store, "MintD")
    assert feed.drain() == 2
    assert first.seen == [3, 4]
    store.close()

    fresh = LedgerStore(str(path))
    try:
        second = _Recorder()
        resumed = PromotionFeed(fresh, second)  # type: ignore[arg-type]
        assert resumed.drain() == 0
        _close(fresh, "MintE")
        assert resumed.drain() == 1
        assert second.seen == [5]
    finally:
        fresh.close()


def test_crash_after_the_stage_row_does_not_advance_the_strategy_twice(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    store = _create(path)
    _close(store, "MintA")
    crashing = _StageThenCrash(store)
    feed = PromotionFeed(store, crashing)  # type: ignore[arg-type]
    _close(store, "MintC")
    with pytest.raises(SimulatedCrash):
        feed.drain()
    store.close()

    fresh = LedgerStore(str(path))
    try:
        second = _Recorder()
        resumed = PromotionFeed(fresh, second)  # type: ignore[arg-type]
        assert resumed.drain() == 0
        assert second.seen == []
        assert crashing.handled == [2]
        assert len(fresh.read(types=["PromotionStageSet"], limit=None)) == 1
    finally:
        fresh.close()


def test_crash_before_any_stage_row_handles_the_row_once(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    store = _create(path)
    _close(store, "MintA")
    crashing = _CrashBeforeStage()
    feed = PromotionFeed(store, crashing)  # type: ignore[arg-type]
    _close(store, "MintC")
    with pytest.raises(SimulatedCrash):
        feed.drain()
    store.close()

    fresh = LedgerStore(str(path))
    try:
        second = _Recorder()
        resumed = PromotionFeed(fresh, second)  # type: ignore[arg-type]
        assert resumed.drain() == 1
        assert second.seen == [2]
        assert resumed.drain() == 0
        assert second.seen == [2]
        assert crashing.handled == [2]
    finally:
        fresh.close()
