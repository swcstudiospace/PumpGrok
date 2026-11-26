<<<<<<< HEAD
"""STR-03: legacy_screening through the runtime equals run_once_replay.

The same recorded dataset runs twice through the same adapter: the
adapter holds no behavior beyond run_once_replay, so fills (full trade
tuples), the ledger sequence and the chain hash are identical. The
legacy ledger carries no attribution refs.
=======
"""STR-03 / criterion 5: legacy_screening through the runtime equals run_once_replay on smoke.

The runtime must produce the same fills and the same net lamports as the existing replay
path, write no strategy_ticket_refs or strategy_state rows, and reach the screening
decision through the existing decision function rather than a copy of it.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

<<<<<<< HEAD
from pathlib import Path

from pumpgrok.backtest.evaluate import CandidateParams
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.strategies.legacy import run_legacy
from pumpgrok.supervisor.scheduler import run_once_replay

SMOKE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "replay" / "smoke"


def test_adapter_parity_with_direct_replay(tmp_path: Path) -> None:
    filter_cfg = CandidateParams().filter_settings()
    direct = run_once_replay(
        SMOKE, filter_cfg, seed=20260101, ledger_path=tmp_path / "direct.sqlite"
    )
    via_adapter = run_legacy(
        SMOKE, filter_cfg, seed=20260101, ledger_path=tmp_path / "adapter.sqlite"
    )
    assert via_adapter.trades == direct.trades
    assert [t.side for t in via_adapter.trades] == [t.side for t in direct.trades]
    assert via_adapter.seq == direct.seq
    assert via_adapter.events_hash == direct.events_hash
    assert len(direct.trades) > 0  # the parity is over a real fill
    assert any(t.outcome == "filled" for t in direct.trades)


def test_legacy_adapter_writes_no_attribution_refs(tmp_path: Path) -> None:
    filter_cfg = CandidateParams().filter_settings()
    run_legacy(SMOKE, filter_cfg, seed=20260101, ledger_path=tmp_path / "legacy.sqlite")
    store = LedgerStore(str(tmp_path / "legacy.sqlite"))
    try:
        notes = store.read(types=["JournalNote"], limit=None)
        refs = [
            row["payload"]["text"]
            for row in notes
            if isinstance(row["payload"], dict)
            and row["payload"].get("note_kind") == "ticket"
            and "strategy" in str(row["payload"].get("text", ""))
        ]
        assert refs == []
    finally:
        store.close()
=======
import sqlite3
from pathlib import Path

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.engine import pipeline
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.strategies import legacy, runtime
from pumpgrok.strategies.attribution import desk_net_lamports
from pumpgrok.supervisor.scheduler import run_once_replay

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SEED = 20260101


def _net(path: Path) -> int:
    store = LedgerStore(str(path))
    try:
        return desk_net_lamports(store)
    finally:
        store.close()


def test_legacy_through_runtime_matches_run_once_replay(tmp_path: Path) -> None:
    reference = run_once_replay(
        SMOKE, FilterSettings(), seed=SEED, ledger_path=tmp_path / "reference.sqlite"
    )
    through = legacy.run_legacy_replay(
        SMOKE, FilterSettings(), seed=SEED, ledger_path=tmp_path / "runtime.sqlite"
    )
    assert reference.trades, "the smoke replay must place orders"
    assert {trade.side for trade in reference.trades} == {"buy", "sell"}, (
        "the parity run must include the exit seat's sell as well as the sniper's buys"
    )
    assert through.trades == reference.trades
    assert _net(through.ledger_path) == _net(reference.ledger_path)


def test_legacy_writes_no_ticket_refs_or_strategy_state(tmp_path: Path) -> None:
    through = legacy.run_legacy_replay(
        SMOKE, FilterSettings(), seed=SEED, ledger_path=tmp_path / "runtime.sqlite"
    )
    with sqlite3.connect(through.ledger_path) as db:
        refs = db.execute("SELECT COUNT(*) FROM strategy_ticket_refs").fetchone()[0]
        states = db.execute("SELECT COUNT(*) FROM strategy_state").fetchone()[0]
    assert refs == 0
    assert states == 0


def test_adapter_reaches_the_existing_screening_function(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert legacy.decide_token is pipeline.decide_token
    calls: list[str] = []
    real = pipeline.decide_token

    def spy(token: object, cfg: object, now: float) -> object:
        calls.append(str(getattr(token, "mint", "")))
        return real(token, cfg, now)  # type: ignore[arg-type]

    monkeypatch.setattr(legacy, "decide_token", spy)
    legacy.run_legacy_replay(SMOKE, FilterSettings(), seed=SEED, ledger_path=tmp_path / "s.sqlite")
    assert len(calls) == 5, "one screening decision per recorded tick"


def test_runtime_module_imports_no_ledger_store() -> None:
    assert not hasattr(runtime, "LedgerStore")
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
