"""RT-03 / criterion 10: an idle event desk makes no Grok call and writes no ledger row.

Offline. The desk is built and started; no event, tick or ledger row arrives. The Grok
transport double records any call, and the ledger row count is taken before and after.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from datafeed.readonly_double import ReadOnlyDouble
from pumpgrok.config.settings import Settings
from pumpgrok.events.event_desk import build_event_desk
from pumpgrok.grok.gateway import GrokRequest
from pumpgrok.replay.clock import FixtureClock

START = 1_700_000_000.0
_SETTLE_ROUNDS = 1_000


class RecordingGrok:
    """GrokTransport double: records each call it is asked to make."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, request: GrokRequest, text: str) -> str:
        self.calls.append(text)
        return "admit"


async def _settle() -> None:
    """Yield until every task the desk spawned has finished. Virtual time does not move."""
    current = asyncio.current_task()
    for _ in range(_SETTLE_ROUNDS):
        pending = {task for task in asyncio.all_tasks() if task is not current and not task.done()}
        if not pending:
            return
        await asyncio.wait(pending)
    raise AssertionError("desk tasks did not settle")


async def test_idle_desk_makes_no_grok_call_and_writes_no_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    grok = RecordingGrok()
    desk = await build_event_desk(
        Settings(mode="paper"),
        data_dir=tmp_path / "desk",
        clock=FixtureClock(START),
        rpc_transport=ReadOnlyDouble(),
        grok_transport=grok,
        strategies=(),
        evidence=lambda _strategy_id: None,
        entry_evidence=lambda _mint: None,
    )
    try:
        await desk.start()
        rows_before = desk.root.store.count()
        await _settle()

        assert grok.calls == []
        assert desk.root.store.count() == rows_before
    finally:
        await desk.close()
