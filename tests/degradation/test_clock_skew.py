"""INV-R-22: clock skew refuses appends with escalation until catch-up.

The backward step rides FixtureClock.jump (no wall clock anywhere); the refusal and
escalation are the product path (append_escalation and its skew precheck against the
ledger head).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.supervisor.seat_relay import CLOCK_SKEW_S, ClockSkew, append_escalation

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


def _heartbeat(store: LedgerStore, clock: FixtureClock, detail: str) -> None:
    append_escalation(
        store,
        clock,
        kind="heartbeat_stale",
        seat="bot-01-scout",
        detail=detail,
        source="replay",
        correlation_id="desk",
    )


def test_backward_jump_refuses_appends_with_escalation(tmp_path: Path) -> None:
    clock = FixtureClock(start=HEAD_TS)
    store = _store(tmp_path)
    try:
        _head(store)
        clock.jump(-30.0)
        assert clock.now() == HEAD_TS - 30.0
        with pytest.raises(ClockSkew):
            _heartbeat(store, clock, "stale")
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
            _heartbeat(store, clock, "stale")
        clock.jump(35.0)
        _heartbeat(store, clock, "caught up")
        kinds = [event["payload"]["kind"] for event in store.read(types=["Escalation"], limit=None)]
        assert kinds == ["clock_skew", "heartbeat_stale"]
        assert store.verify() is True
    finally:
        store.close()
