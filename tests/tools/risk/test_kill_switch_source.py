"""Regression (WR-07): kill-switch status reports the real engagement source.

A ledger-engaged switch (the command path) reports ``command``, not ``none``;
env and file causes keep their own origin and take precedence over the ledger.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import pytest

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.risk.kill_switch import KillSwitchIn, _status, build_kill_switch_tool

START = 1469918176.385


@pytest.fixture(autouse=True)
def _no_env_killswitch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PUMPGROK_KILLSWITCH", raising=False)


def _store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(str(tmp_path / "ledger.sqlite"))


def test_nothing_engaged_reports_none(tmp_path: Path) -> None:
    store = _store(tmp_path)
    view = _status(store, tmp_path / "KILLSWITCH", "corr", FixtureClock(start=START))
    store.close()
    assert view["active"] is False
    assert view["source"] == "none"


async def test_ledger_set_reports_command(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tool = build_kill_switch_tool(store, FixtureClock(start=START))
    out = await tool(KillSwitchIn(action="set", reason="manual test"))
    store.close()
    assert out.active is True
    assert out.source == "command"


async def test_ledger_flatten_request_reports_command(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tool = build_kill_switch_tool(store, FixtureClock(start=START))
    out = await tool(KillSwitchIn(action="flatten_request", reason="close all"))
    store.close()
    assert out.active is True
    assert out.flatten_requested is True
    assert out.source == "command"


async def test_file_engagement_reports_file(tmp_path: Path) -> None:
    store = _store(tmp_path)
    killswitch = tmp_path / "KILLSWITCH"
    killswitch.write_text("", encoding="utf-8")
    tool = build_kill_switch_tool(store, FixtureClock(start=START), killswitch)
    out = await tool(KillSwitchIn(action="set", reason="file probe"))
    store.close()
    assert out.active is True
    assert out.source == "file"


async def test_env_engagement_reports_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path)
    monkeypatch.setenv("PUMPGROK_KILLSWITCH", "1")
    tool = build_kill_switch_tool(store, FixtureClock(start=START))
    out = await tool(KillSwitchIn(action="set", reason="env probe"))
    store.close()
    assert out.active is True
    assert out.source == "env"
