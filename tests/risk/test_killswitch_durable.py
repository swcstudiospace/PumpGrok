"""S-K4: latch and escalation writes are fsynced and atomic; a failed write keeps the old latch.

Also: the clear removes only the latch content it read, and the kill tool writes the latch
through the same durable writer.
"""

from __future__ import annotations

import os
import random
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.ids import IdFactory
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.killswitch import KillSwitch, killswitch_file, latch_from_alert
from pumpgrok.tools.risk.kill_switch import KillSwitchIn, run_kill_switch

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()


def _human_clear(clock: FixtureClock, ids: IdFactory) -> ApprovalRecord:
    return ApprovalRecord(
        id=f"apr-{ids.ulid()}",
        kind="killswitch_clear",
        approved_by="human:alice",
        raw_message="human clear",
        at=datetime.fromtimestamp(clock.now(), UTC),
    )


def test_latch_write_fsyncs_the_file_and_its_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    synced: list[int] = []
    real_fsync = os.fsync

    def record(fd: int) -> None:
        synced.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", record)
    latch_from_alert("KILL halt", killswitch_file(tmp_path))
    assert len(synced) >= 2
    assert killswitch_file(tmp_path).read_text(encoding="utf-8") == "halt"


def test_failed_fsync_keeps_the_old_latch_and_leaves_no_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    latch = killswitch_file(tmp_path)
    latch.write_text("old", encoding="utf-8")

    def fail(fd: int) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError):
        latch_from_alert("KILL halt", latch)
    assert latch.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob("*.tmp")) == []


def test_escalation_write_is_fsynced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    latch = killswitch_file(tmp_path)
    latch.write_text("halt", encoding="utf-8")
    ks = KillSwitch(FixtureClock(start=START), killswitch_path=latch, env={})
    synced: list[int] = []
    real_fsync = os.fsync

    def record(fd: int) -> None:
        synced.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", record)
    assert ks._escalate("go flat") is True
    assert len(synced) >= 2
    assert latch.read_text(encoding="utf-8") == "FLATTEN go flat"


async def test_kill_tool_writes_the_latch_through_the_durable_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    synced: list[int] = []
    real_fsync = os.fsync

    def record(fd: int) -> None:
        synced.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", record)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        await run_kill_switch(
            KillSwitchIn(action="set", reason="halt"),
            store,
            FixtureClock(start=START),
            killswitch_file(tmp_path),
        )
    finally:
        store.close()
    assert len(synced) >= 2
    assert killswitch_file(tmp_path).read_text(encoding="utf-8") == "halt"


def test_clear_keeps_a_latch_written_while_the_clear_ran(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FixtureClock(start=START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    ids = IdFactory(clock, random.Random(7))
    latch = killswitch_file(tmp_path)
    latch.write_text("old cause", encoding="utf-8")
    ks = KillSwitch(clock, store=store, killswitch_path=latch, env={})
    real_append = store.append_batch

    def land_a_new_kill(rows: list) -> None:
        latch.write_text("new cause", encoding="utf-8")
        return real_append(rows)

    monkeypatch.setattr(store, "append_batch", land_a_new_kill)
    try:
        ks.request_clear(_human_clear(clock, ids), "all clear", ts_utc=format_ts_utc(START))
        assert latch.read_text(encoding="utf-8") == "new cause"
    finally:
        store.close()
