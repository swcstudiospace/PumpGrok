"""Missing genesis equity fails closed in the paper composition root.

The operator composition root used to write ``initial_equity_lamports`` from
the configured budget whenever the meta row was absent, even when the ledger
already held history. If the row was lost, startup silently changed the base
used for balances and risk checks. A missing genesis on a non-empty ledger
now raises ``CorruptState``; only a new, empty ledger gets genesis written.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from pumpgrok.config.settings import load_settings
from pumpgrok.core.errors import CorruptState
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.tools import build_operator_registry, ensure_paper_genesis

ROOT = Path(__file__).resolve().parents[2]
START = 1_700_000_000.0
CID = "01JAAAAAAAAAAAAAAAAAAAAAAAAA"


def _seed_history(ledger: Path, *, genesis: str | None) -> None:
    """Create a ledger with one neutral event and an optional genesis meta row."""
    store = LedgerStore(str(ledger))
    try:
        if genesis is not None:
            store.set_meta("initial_equity_lamports", genesis)
        store.append(
            ts_utc=format_ts_utc(FixtureClock(start=START).now()),
            source="paper",
            correlation_id=CID,
            idempotency_key="history",
            type="JournalNote",
            payload={
                "source": "paper",
                "seat": "desk",
                "note_kind": "note",
                "text": "history without genesis",
            },
        )
    finally:
        store.close()


def _compose(tmp_path: Path, ledger: Path) -> None:
    """Run the operator composition root over ``ledger``; close its HTTP client."""
    _reg, _manifests, client = build_operator_registry(
        data_dir=tmp_path / "desk",
        repo_root=ROOT,
        settings=load_settings(),
        clock=FixtureClock(start=START),
        ledger_path=ledger,
        p_drop=0.0,
    )
    asyncio.run(client.aclose())


def test_missing_genesis_on_existing_history_raises(tmp_path: Path) -> None:
    """History without genesis raises CorruptState and is not given a default."""
    ledger = tmp_path / "ledger.sqlite"
    _seed_history(ledger, genesis=None)

    with pytest.raises(CorruptState) as excinfo:
        _compose(tmp_path, ledger)

    assert excinfo.value.code == "corrupt_state"
    store = LedgerStore(str(ledger))
    try:
        assert store.get_meta("initial_equity_lamports") is None
    finally:
        store.close()


def test_present_genesis_on_existing_history_loads(tmp_path: Path) -> None:
    """A ledger with its genesis loads and keeps the recorded value."""
    ledger = tmp_path / "ledger.sqlite"
    _seed_history(ledger, genesis="12345")

    _compose(tmp_path, ledger)

    store = LedgerStore(str(ledger))
    try:
        assert store.get_meta("initial_equity_lamports") == "12345"
    finally:
        store.close()


def test_new_empty_ledger_gets_genesis_from_budget(tmp_path: Path) -> None:
    """Only a new, empty ledger has its genesis initialized from the budget."""
    ledger = tmp_path / "ledger.sqlite"
    store = LedgerStore(str(ledger))
    store.close()

    _compose(tmp_path, ledger)

    store = LedgerStore(str(ledger))
    try:
        expected = str(load_settings().risk.paper_equity_lamports)
        assert store.get_meta("initial_equity_lamports") == expected
    finally:
        store.close()


def test_ensure_paper_genesis_is_written_first_then_noop(tmp_path: Path) -> None:
    """An empty ledger gets genesis before any event; a later call changes nothing."""
    ledger = tmp_path / "ledger.sqlite"
    budget = RiskBudget()
    store = LedgerStore(str(ledger))
    try:
        ensure_paper_genesis(store, budget)
        assert store.count() == 0
        assert store.get_meta("initial_equity_lamports") == str(budget.paper_equity_lamports)
        ensure_paper_genesis(store, RiskBudget(paper_equity_sol=Decimal("20")))
        assert store.get_meta("initial_equity_lamports") == str(budget.paper_equity_lamports)
    finally:
        store.close()
