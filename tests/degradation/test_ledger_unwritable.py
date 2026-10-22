"""INV-R-20: unwritable ledger refuses orders into a bounded buffer, then drains.

The fault is injected at the store boundary through FaultyLedgerStore; the
assertions drive product code (DegradedState buffer/drain, Escalation rows,
LedgerStore.verify) and prove the fault fired before recovery is claimed.
"""

from __future__ import annotations

import errno
from pathlib import Path

import pytest

from harness.faults import FaultInjector, FaultMode, FaultyLedgerStore
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.supervisor.scheduler import LEDGER_BUFFER_CAP, DegradedState, LedgerUnavailable
from pumpgrok.supervisor.seat_task import append_escalation

BASE = 1767225600.0


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))


def _row(index: int) -> dict:
    return {
        "ts_utc": format_ts_utc(BASE + index),
        "source": "paper",
        "correlation_id": "desk",
        "idempotency_key": f"k-{index}",
        "type": "JournalNote",
        "payload": {
            "source": "paper",
            "seat": "desk",
            "note_kind": "note",
            "text": "t",
            "refs": [],
        },
    }


def test_unwritable_store_refuses_appends_with_eacces(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        faulty = FaultyLedgerStore(store)
        with pytest.raises(PermissionError) as excinfo:
            faulty.append(**_row(0))
        assert excinfo.value.errno == errno.EACCES
        assert faulty.fired == 1
        assert store.count() == 0
        assert faulty.verify() is True
    finally:
        store.close()


def test_unwritable_store_buffers_1000_then_refuses_and_drains(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        faulty = FaultyLedgerStore(store)
        degraded = DegradedState(ledger_writable=False)
        with pytest.raises(PermissionError):
            faulty.append_batch([_row(0)])
        assert faulty.fired == 1
        assert store.count() == 0
        for index in range(LEDGER_BUFFER_CAP):
            degraded.buffer_order(_row(index))
        with pytest.raises(LedgerUnavailable):
            degraded.buffer_order(_row(LEDGER_BUFFER_CAP))
        append_escalation(
            store,
            clock,
            kind="persistence_down",
            seat="desk",
            detail="ledger unwritable; buffering",
            source="paper",
            correlation_id="desk",
        )
        kinds = [event["payload"]["kind"] for event in store.read(types=["Escalation"], limit=None)]
        assert kinds == ["persistence_down"]
        drained = degraded.drain_buffer(store)
        assert drained == LEDGER_BUFFER_CAP
        assert degraded.ledger_buffer == []
        assert degraded.persistence_raised is False
        assert store.count() == LEDGER_BUFFER_CAP + 1
        assert store.verify() is True
    finally:
        store.close()


def test_sink_unwritable_raises_eacces(tmp_path: Path) -> None:
    injector = FaultInjector(FaultMode.UNWRITABLE)
    with pytest.raises(PermissionError) as excinfo, injector.open_sink(tmp_path / "sink.jsonl"):
        pass
    assert excinfo.value.errno == errno.EACCES
