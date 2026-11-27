"""S-K1 / S-K2: a bare or FLATTEN-led kill reason is never a command or a latch body.

The kill tool refuses a FLATTEN-led reason before it writes the ledger row.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.risk.killswitch import kill_file_text, parse_kill_line
from pumpgrok.tools.risk.kill_switch import KillSwitchIn, run_kill_switch

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()


def test_bare_kill_flatten_is_not_a_command() -> None:
    assert parse_kill_line("KILL FLATTEN") is None


def test_flatten_led_reason_after_the_flag_is_not_a_command() -> None:
    assert parse_kill_line("KILL FLATTEN FLATTEN x") is None


def test_flatten_with_a_real_reason_still_parses() -> None:
    assert parse_kill_line("KILL FLATTEN now") == (True, "now")


def test_file_writer_refuses_a_flatten_led_plain_reason() -> None:
    with pytest.raises(ValueError):
        kill_file_text("FLATTEN x", False)


def test_file_writer_still_writes_a_flatten_request() -> None:
    assert kill_file_text("halt now", True) == "FLATTEN halt now"


@pytest.mark.parametrize("action", ["set", "flatten_request"])
async def test_kill_tool_refuses_a_flatten_led_reason_before_the_ledger_row(
    tmp_path: Path, action: str
) -> None:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        with pytest.raises(ValueError):
            await run_kill_switch(
                KillSwitchIn(action=action, reason="FLATTEN x"),  # type: ignore[arg-type]
                store,
                FixtureClock(start=START),
                tmp_path / "KILLSWITCH",
            )
        assert store.read(types=["KillSwitchSet"], limit=None) == []
        assert not (tmp_path / "KILLSWITCH").exists()
    finally:
        store.close()
