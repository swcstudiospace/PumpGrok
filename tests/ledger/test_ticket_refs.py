"""STR-03: ticket attribution refs; legacy_screening writes none."""

from __future__ import annotations

from pathlib import Path

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.strategy_state import read_attribution_refs, record_attribution_ref


def _open_store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(str(tmp_path / "ledger.sqlite"))


def test_new_strategy_refs_round_trip(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        assert (
            record_attribution_ref(
                store,
                strategy_id="momentum_breakout",
                ticket_id="SOL-20260101-001",
                mint="MintA",
                ts_utc="2026-01-01T00:00:00Z",
                source="paper",
                correlation_id="ticket-ref-1",
            )
            == "SOL-20260101-001"
        )
        assert read_attribution_refs(store, "momentum_breakout") == [
            {"ticket_id": "SOL-20260101-001", "mint": "MintA"}
        ]
    finally:
        store.close()


def test_legacy_writes_no_refs(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        assert (
            record_attribution_ref(
                store,
                strategy_id="legacy_screening",
                ticket_id="SOL-20260101-001",
                mint="MintA",
                ts_utc="2026-01-01T00:00:00Z",
                source="paper",
                correlation_id="ticket-ref-2",
            )
            is None
        )
        assert read_attribution_refs(store, "legacy_screening") == []
        assert read_attribution_refs(store, "momentum_breakout") == []
    finally:
        store.close()
