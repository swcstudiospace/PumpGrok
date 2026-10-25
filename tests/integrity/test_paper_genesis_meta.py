"""INT-02: the paper composition root records genesis equity at startup.

The replay composition root writes ``initial_equity_lamports`` when it opens
its ledger; the paper (operator registry) root did not, so a fresh paper
ledger failed closed: shutdown and the exit seat's protective halt raised
``CorruptState`` instead of running. The paper composition now writes the
same meta row from the configured budget at genesis, and never overwrites an
existing genesis.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pumpgrok.config.settings import load_settings
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.supervisor.lifecycle import shutdown
from pumpgrok.supervisor.scheduler import ROSTER, Supervisor
from pumpgrok.supervisor.seat_task import SeatContext, SeatTask
from pumpgrok.tools import build_operator_registry

ROOT = Path(__file__).resolve().parents[2]
START = 1_700_000_000.0


async def _ok(ctx: SeatContext) -> dict[str, Any]:
    return {"ok": True}


async def _compose(tmp_path: Path, name: str = "ledger.sqlite") -> Path:
    """Run the paper composition root over a fresh ledger; return its path."""
    ledger = tmp_path / name
    assert not ledger.exists()
    settings = load_settings()
    _reg, _manifests, client = build_operator_registry(
        data_dir=tmp_path / "desk",
        repo_root=ROOT,
        settings=settings,
        clock=FixtureClock(start=START),
        ledger_path=ledger,
        p_drop=0.0,
    )
    await client.aclose()
    return ledger


def test_paper_composition_records_genesis_equity(tmp_path: Path) -> None:
    """The fresh paper ledger carries the configured budget as genesis equity."""
    ledger = asyncio.run(_compose(tmp_path))
    expected = str(load_settings().risk.paper_equity_lamports)
    store = LedgerStore(str(ledger))
    try:
        assert store.get_meta("initial_equity_lamports") == expected
    finally:
        store.close()


def test_paper_composition_never_overwrites_genesis(tmp_path: Path) -> None:
    """History keeps the genesis it started with when the budget later changes."""
    ledger = tmp_path / "ledger.sqlite"
    pre = LedgerStore(str(ledger))
    try:
        pre.set_meta("initial_equity_lamports", "12345")
    finally:
        pre.close()
    settings = load_settings()
    assert str(settings.risk.paper_equity_lamports) != "12345"
    _reg, _manifests, client = build_operator_registry(
        data_dir=tmp_path / "desk",
        repo_root=ROOT,
        settings=settings,
        clock=FixtureClock(start=START),
        ledger_path=ledger,
        p_drop=0.0,
    )
    asyncio.run(client.aclose())
    store = LedgerStore(str(ledger))
    try:
        assert store.get_meta("initial_equity_lamports") == "12345"
    finally:
        store.close()


async def test_fresh_paper_ledger_reaches_shutdown(tmp_path: Path) -> None:
    """Shutdown snapshots a fresh paper ledger instead of raising CorruptState."""
    ledger = await _compose(tmp_path)
    clock = FixtureClock(start=START)
    store = LedgerStore(str(ledger))
    try:
        supervisor = Supervisor(
            store=store, clock=clock, rng=make_rng(11), cycles=dict.fromkeys(ROSTER, _ok)
        )
        code = await shutdown(
            supervisor,
            store=store,
            health_path=str(tmp_path / "health.json"),
            journal_dir=str(tmp_path / "journal"),
            trades_path=str(tmp_path / "trades.jsonl"),
        )
        assert code == 0
    finally:
        store.close()


async def test_fresh_paper_ledger_reaches_exit_halt(tmp_path: Path) -> None:
    """The exit seat's protective halt lands instead of raising CorruptState."""
    ledger = await _compose(tmp_path)
    clock = FixtureClock(start=START)
    store = LedgerStore(str(ledger))
    try:
        task = SeatTask("bot-06-exit", 1.0, _ok, clock=clock, rng=make_rng(11), store=store)
        task._append_exit_halt("test-correlation")
        halts = store.read(types=["HaltSet"], limit=None)
        assert len(halts) == 1
        assert halts[0]["payload"]["reason"] == "manual"
    finally:
        store.close()
