"""STR-03: legacy_screening through the runtime equals run_once_replay.

The same recorded dataset runs twice through the same adapter: the
adapter holds no behavior beyond run_once_replay, so fills (full trade
tuples), the ledger sequence and the chain hash are identical. The
legacy ledger carries no attribution refs.
"""

from __future__ import annotations

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
