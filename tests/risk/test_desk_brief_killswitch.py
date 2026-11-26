"""S-K5: the desk brief reads the real kill file and reports a latched kill switch."""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.risk.killswitch import killswitch_file
from pumpgrok.tools.desk._memory import MemoryBank
from pumpgrok.tools.desk.brief import BriefIn, build_brief_tool

START = 1469918176.385


@pytest.fixture(autouse=True)
def _no_env_killswitch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PUMPGROK_KILLSWITCH", raising=False)


async def test_brief_reports_a_latched_kill_switch(tmp_path: Path) -> None:
    data_dir = tmp_path / "desk"
    data_dir.mkdir()
    killswitch_file(data_dir).write_text("operator stop", encoding="utf-8")
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    bank = MemoryBank(tmp_path / "memory.jsonl")
    try:
        tool = build_brief_tool(
            store, bank, FixtureClock(start=START), killswitch_file(data_dir), mode="paper"
        )
        out = await tool(BriefIn(task_id="t-1"))
        assert out.halt["kill_switch_active"] is True
    finally:
        store.close()
