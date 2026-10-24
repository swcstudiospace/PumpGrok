"""F1: a same-day re-engagement after an approved clear writes its own ``KillSwitchSet`` row.

F6: a flatten whose adapter raises a non-Pumpgrok error for one position still attempts and
closes every other position, and records the failed one as ``not_flattened``.
"""

from __future__ import annotations

import logging
import random
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pumpgrok.core.approvals import ApprovalRecord
from pumpgrok.core.ids import IdFactory
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.killswitch import InflightBarrier, KillSwitch, killswitch_file
from pumpgrok.tools.risk.kill_switch import FlattenIntent, execute_flatten

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
MINT_A = "So11111111111111111111111111111111111111112"
MINT_B = "So22222222222222222222222222222222222222222"
KILL_LOGGER = "pumpgrok.tools.risk.kill_switch"
SECRET = "xai-" + "A" * 32


def _store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(str(tmp_path / "ledger.sqlite"))


def _human_clear(clock: FixtureClock, ids: IdFactory) -> ApprovalRecord:
    return ApprovalRecord(
        id=f"apr-{ids.ulid()}",
        kind="killswitch_clear",
        approved_by="human:alice",
        raw_message="human clear",
        at=datetime.fromtimestamp(clock.now(), UTC),
    )


def test_set_clear_set_on_the_same_day_leaves_the_second_engagement_open(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    latch = killswitch_file(tmp_path)
    try:
        ks = KillSwitch(clock, store=store, killswitch_path=latch, env={})
        latch.write_text("operator stop", encoding="utf-8")
        assert ks.observe(ts_utc=format_ts_utc(START), correlation_id="t") is not None
        latch.unlink()
        ks.request_clear(_human_clear(clock, ids), "all clear", ts_utc=format_ts_utc(START))
        assert ks.poll().active is False

        latch.write_text("operator stop", encoding="utf-8")
        second = ks.observe(ts_utc=format_ts_utc(START), correlation_id="t")
        assert second is not None
        assert second["payload"]["origin"] == "file"
        assert len(store.read(types=["KillSwitchSet"], limit=None)) == 2

        # Repeat observation the same day still writes nothing: the open row is the record.
        assert ks.observe(ts_utc=format_ts_utc(START), correlation_id="t") is None

        # Deleting the latch file no longer disengages: the ledger holds an open set row
        # that only an approved human clear can close.
        latch.unlink()
        state = ks.poll()
        assert state.active is True
        assert state.source == "file"
    finally:
        store.close()


async def test_a_non_pumpgrok_error_on_one_position_does_not_stop_the_flatten() -> None:
    barrier = InflightBarrier()
    closed: list[str] = []

    async def close_position(*, mint: str, ticket_id: str, reason: str) -> dict[str, str]:
        if mint == MINT_A:
            raise RuntimeError("adapter exploded")
        closed.append(mint)
        return {"status": "closed"}

    intents = [
        FlattenIntent(mint=MINT_A, ticket_id="T-A", token_units=5),
        FlattenIntent(mint=MINT_B, ticket_id="T-B", token_units=7),
    ]
    result = await execute_flatten(lambda: intents, barrier=barrier, close_position=close_position)

    assert result.status == "completed"
    assert closed == [MINT_B]
    assert [(o.mint, o.status, o.detail) for o in result.outcomes] == [
        (MINT_A, "not_flattened", "RuntimeError"),
        (MINT_B, "closed", ""),
    ]


async def test_a_failing_close_is_logged_with_mint_and_class_and_detail_stays_the_class(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=KILL_LOGGER)
    barrier = InflightBarrier()

    async def close_position(*, mint: str, ticket_id: str, reason: str) -> dict[str, str]:
        raise RuntimeError(f"close refused for key {SECRET}")

    intents = [FlattenIntent(mint=MINT_A, ticket_id="T-A", token_units=5)]
    result = await execute_flatten(lambda: intents, barrier=barrier, close_position=close_position)

    assert [(o.mint, o.status, o.detail) for o in result.outcomes] == [
        (MINT_A, "not_flattened", "RuntimeError")
    ]
    records = [r for r in caplog.records if r.name == KILL_LOGGER]
    assert len(records) == 1
    message = records[0].getMessage()
    assert MINT_A in message
    assert "RuntimeError" in message
    # The logged message is redacted: the secret-shaped value never reaches the log.
    assert SECRET not in caplog.text
    assert "xai-" + "*" * 32 in message


def test_a_clear_landing_during_the_poll_is_not_undone_by_the_observation(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    ids = IdFactory(clock, random.Random(7))
    latch = killswitch_file(tmp_path)
    try:
        ks = KillSwitch(clock, store=store, killswitch_path=latch, env={})
        latch.write_text("operator stop", encoding="utf-8")
        assert ks.observe(ts_utc=format_ts_utc(START), correlation_id="t") is not None
        latch.unlink()

        real_poll = ks.poll

        def poll_while_a_clear_lands():
            state = real_poll()
            ks.request_clear(_human_clear(clock, ids), "all clear", ts_utc=format_ts_utc(START))
            return state

        ks.poll = poll_while_a_clear_lands
        assert ks.observe(ts_utc=format_ts_utc(START), correlation_id="t") is None
        assert len(store.read(types=["KillSwitchSet"], limit=None)) == 1
        assert len(store.read(types=["KillSwitchCleared"], limit=None)) == 1
    finally:
        store.close()
