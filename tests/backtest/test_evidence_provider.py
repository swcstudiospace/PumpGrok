"""Evidence provider: registered run readable, unknown refuses, fixture never promotes."""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.backtest.evidence import BacktestEvidenceProvider
from pumpgrok.backtest.store import RunStore


def _store(tmp_path: Path) -> RunStore:
    store = RunStore(tmp_path / "runs.jsonl")
    store.save(
        {
            "idempotence_key": "digest:legacy_screening:h1",
            "kind": "run",
            "strategy_id": "legacy_screening",
            "param_hash": "h1",
            "result": {"eligible": True, "reasons": ["pass"], "kind": "recorded"},
        }
    )
    store.save(
        {
            "idempotence_key": "digest:legacy_screening:h2",
            "kind": "run",
            "strategy_id": "legacy_screening",
            "param_hash": "h2",
            "result": {"eligible": True, "reasons": ["pass"], "kind": "fixture"},
        }
    )
    return store


def test_registered_run_is_gate_readable(tmp_path: Path) -> None:
    provider = BacktestEvidenceProvider(_store(tmp_path))
    evidence = provider.get("legacy_screening", "h1")
    assert evidence["eligible"] is True
    assert evidence["record"]["param_hash"] == "h1"


def test_unknown_pair_refuses(tmp_path: Path) -> None:
    provider = BacktestEvidenceProvider(_store(tmp_path))
    with pytest.raises(KeyError):
        provider.get("legacy_screening", "missing")


def test_fixture_data_never_promotes(tmp_path: Path) -> None:
    provider = BacktestEvidenceProvider(_store(tmp_path))
    assert provider.get("legacy_screening", "h2")["eligible"] is False
