"""INV-R-22: clock skew refuses appends with escalation until catch-up.

The backward step rides FixtureClock.jump (no wall clock anywhere); the
refusal and escalation are the product paths (assert_no_skew,
append_escalation, DegradedState.skew_detected).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc, parse_ts_utc
from pumpgrok.supervisor.scheduler import DegradedState, assert_no_skew
from pumpgrok.supervisor.seat_task import CLOCK_SKEW_S, ClockSkew, append_escalation

HEAD_TS = 1_000.0


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))


def _head(store: LedgerStore) -> None:
    store.append(
        ts_utc=format_ts_utc(HEAD_TS),
        source="replay",
        correlation_id="desk",
        idempotency_key="head",
        type="JournalNote",
        payload={
            "source": "replay",
            "seat": "desk",
            "note_kind": "note",
            "text": "head",
            "refs": [],
        },
    )


def test_backward_jump_refuses_appends_with_escalation(tmp_path: Path) -> None:
    clock = FixtureClock(start=HEAD_TS)
    store = _store(tmp_path)
    try:
        _head(store)
        clock.jump(-30.0)
        assert clock.now() == HEAD_TS - 30.0
        assert DegradedState.skew_detected(clock.now(), HEAD_TS) is True
        with pytest.raises(ClockSkew):
            assert_no_skew(store, clock)
        with pytest.raises(ClockSkew):
            append_escalation(
                store,
                clock,
                kind="heartbeat_stale",
                seat="bot-01-scout",
                detail="stale",
                source="replay",
                correlation_id="desk",
            )
        kinds = [event["payload"]["kind"] for event in store.read(types=["Escalation"], limit=None)]
        assert kinds == ["clock_skew"]
        assert CLOCK_SKEW_S == 5.0
    finally:
        store.close()


def test_catch_up_clears_skew_and_appends_resume(tmp_path: Path) -> None:
    clock = FixtureClock(start=HEAD_TS)
    store = _store(tmp_path)
    try:
        _head(store)
        clock.jump(-30.0)
        with pytest.raises(ClockSkew):
            assert_no_skew(store, clock)
        clock.jump(35.0)
        assert DegradedState.skew_detected(clock.now(), HEAD_TS) is False
        assert_no_skew(store, clock)
        store.append(
            ts_utc=format_ts_utc(clock.now()),
            source="replay",
            correlation_id="desk",
            idempotency_key="after-catch-up",
            type="JournalNote",
            payload={
                "source": "replay",
                "seat": "desk",
                "note_kind": "note",
                "text": "caught up",
                "refs": [],
            },
        )
        stamps = [parse_ts_utc(str(row["ts_utc"])) for row in store.read(limit=None)]
        assert stamps[-1] == clock.now()
        assert store.verify() is True
    finally:
        store.close()
