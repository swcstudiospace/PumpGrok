"""RT-03/PRM-05: the paper event desk wires risk checks and refuses non-paper.

The composition root builds the full paper desk and refuses any
non-paper mode before adapters exist; entry-gate checks are wired into
the live-paper root through the same hook.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.adapter import ExecutionMode
from pumpgrok.execution.entry_hook import EntryHook, EntryRefusedError
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.risk.entry_checks import EntryChecks, MintFacts
from pumpgrok.supervisor.event_desk import EventDeskError, build_event_desk
from pumpgrok.supervisor.live_paper import LivePaperError, build_live_paper

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
MINT_OK = "So11111111111111111111111111111111111111112"


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", "10000000000")
    store.set_meta("source", "paper")
    return store


def test_event_desk_refuses_non_paper_mode(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    with pytest.raises(EventDeskError):
        build_event_desk(
            mode="live",
            store=store,
            clock=clock,
            place=lambda intent: None,
            sidecar_path=tmp_path / "sidecar.sqlite",
        )


def test_event_desk_builds_with_paper_mode(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    desk = build_event_desk(
        mode=ExecutionMode.PAPER,
        store=store,
        clock=clock,
        place=lambda intent: None,
        sidecar_path=tmp_path / "sidecar.sqlite",
        params={"momentum_breakout": {"breakout_bps": 100}},
    )
    assert desk.mode == str(ExecutionMode.PAPER)
    assert desk.bus is not None
    assert desk.risk is not None
    assert desk.gateway is not None
    assert desk.router is not None
    assert desk.runtime is not None
    assert desk.evaluator is not None


def test_live_paper_refuses_non_paper_mode(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    with pytest.raises(LivePaperError):
        build_live_paper(mode="live", store=store, clock=clock, place=lambda intent: None)


def test_entry_checks_wired_into_live_paper_root(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    desk = build_live_paper(
        mode=ExecutionMode.PAPER,
        store=store,
        clock=clock,
        place=lambda intent: None,
        entry_checks=EntryChecks(),
        params={"momentum_breakout": {"breakout_bps": 100}},
    )
    assert desk.entry_checks is not None
    assert isinstance(desk.entry_hook, EntryHook)
    with pytest.raises(EntryRefusedError):
        desk.entry_hook.check_place(
            side="buy",
            curve_source="replay",
            entry_checks=desk.entry_checks,
            mint_facts=MintFacts(mint=MINT_OK, authority_present=True),
        )
