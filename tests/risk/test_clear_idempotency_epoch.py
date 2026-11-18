"""S-K3: a same-day re-clear with the same reason after a re-engage succeeds.

Also: a retry with the same approval, after a clear whose latch removal failed, removes the
latch without writing a second ``KillSwitchCleared`` row.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from pathlib import Path

import pytest

import pumpgrok.risk.killswitch as killswitch_module
from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.ids import IdFactory
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.killswitch import KillSwitch, killswitch_file

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()


def _human_clear(clock: FixtureClock, ids: IdFactory) -> ApprovalRecord:
    return ApprovalRecord(
        id=f"apr-{ids.ulid()}",
        kind="killswitch_clear",
        approved_by="human:alice",
        raw_message="human clear",
        at=datetime.fromtimestamp(clock.now(), UTC),
    )


def test_same_day_reclear_with_the_same_reason_after_reengage_succeeds(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    ids = IdFactory(clock, random.Random(7))
    latch = killswitch_file(tmp_path)
    try:
        ks = KillSwitch(clock, store=store, killswitch_path=latch, env={})
        latch.write_text("operator stop", encoding="utf-8")
        assert ks.observe(ts_utc=format_ts_utc(START), correlation_id="t") is not None
        ks.request_clear(_human_clear(clock, ids), "all clear", ts_utc=format_ts_utc(START))

        latch.write_text("operator stop", encoding="utf-8")
        assert ks.observe(ts_utc=format_ts_utc(START), correlation_id="t") is not None
        cleared = ks.request_clear(
            _human_clear(clock, ids), "all clear", ts_utc=format_ts_utc(START)
        )
        assert cleared["type"] == "KillSwitchCleared"
        assert len(store.read(types=["KillSwitchCleared"], limit=None)) == 2
        assert ks.poll().active is False
    finally:
        store.close()


def test_retry_with_the_same_approval_removes_the_latch_without_a_second_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FixtureClock(start=START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    ids = IdFactory(clock, random.Random(7))
    latch = killswitch_file(tmp_path)
    try:
        ks = KillSwitch(clock, store=store, killswitch_path=latch, env={})
        latch.write_text("operator stop", encoding="utf-8")
        approval = _human_clear(clock, ids)

        real_remove = killswitch_module._remove_durable

        def failing_remove(path: Path) -> None:
            raise OSError("latch removal failed")

        monkeypatch.setattr(killswitch_module, "_remove_durable", failing_remove)
        with pytest.raises(OSError):
            ks.request_clear(approval, "all clear", ts_utc=format_ts_utc(START))
        assert len(store.read(types=["KillSwitchCleared"], limit=None)) == 1
        assert latch.exists()

        monkeypatch.setattr(killswitch_module, "_remove_durable", real_remove)
        retried = ks.request_clear(approval, "all clear", ts_utc=format_ts_utc(START))
        assert retried["payload"]["approval_id"] == approval.id
        assert not latch.exists()
        assert len(store.read(types=["KillSwitchCleared"], limit=None)) == 1
        assert ks.poll().active is False
    finally:
        store.close()
