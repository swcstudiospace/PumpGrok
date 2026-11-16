"""BT-13: BacktestEvidenceProvider is read-only and feeds the existing gate."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from pumpgrok.backtest.evidence import BacktestEvidenceProvider
from pumpgrok.backtest.store import ResultStore
from pumpgrok.upgrade.gate import GateVerdict, evaluate_candidate
from pumpgrok.upgrade.scheduled import apply_candidate

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "src" / "pumpgrok" / "backtest" / "evidence.py"


def _store(tmp_path: Path) -> ResultStore:
    store = ResultStore(tmp_path / "results.sqlite")
    store.insert_or_get(
        ("a" * 64, "version-1", "params-1", "1"),
        {
            "dataset_digest": "a" * 64,
            "grade": "research_only",
            "grader_version": "1",
            "params_hash": "params-1",
            "reasons": ["synthetic", "short"],
            "result_id": "r" * 64,
            "strategy_version_id": "version-1",
        },
    )
    return store


def test_research_only_is_returned_with_reasons(tmp_path: Path) -> None:
    record = BacktestEvidenceProvider(_store(tmp_path)).evidence_for("version-1", "params-1")
    assert record.absent is False
    assert record.grade == "research_only"
    assert record.reasons == ("synthetic", "short")
    assert record.dataset_digest == "a" * 64
    assert record.result_id == "r" * 64


def test_unknown_key_is_absent_not_eligible(tmp_path: Path) -> None:
    record = BacktestEvidenceProvider(_store(tmp_path)).evidence_for("missing", "missing")
    assert record.absent is True
    assert record.grade != "promotion_eligible"
    assert record.reasons == ()
    assert record.dataset_digest is None
    assert record.result_id is None


def test_non_eligible_grade_is_research_only(tmp_path: Path) -> None:
    store = ResultStore(tmp_path / "results.sqlite")
    store.insert_or_get(
        ("b" * 64, "version-2", "params-2", "1"),
        {
            "dataset_digest": "b" * 64,
            "grade": "fixture",
            "grader_version": "1",
            "params_hash": "params-2",
            "reasons": ["fixture"],
            "result_id": "q" * 64,
            "strategy_version_id": "version-2",
        },
    )
    record = BacktestEvidenceProvider(store).evidence_for("version-2", "params-2")
    assert record.grade == "research_only"
    assert record.reasons == ("fixture",)


def test_reads_do_not_change_the_store_file(tmp_path: Path) -> None:
    store = _store(tmp_path)
    before = hashlib.sha256(store.path.read_bytes()).hexdigest()
    provider = BacktestEvidenceProvider(store)
    provider.evidence_for("version-1", "params-1")
    provider.evidence_for("missing", "missing")
    assert hashlib.sha256(store.path.read_bytes()).hexdigest() == before


def test_provider_feeds_existing_gate_input_and_defines_no_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = ast.parse(EVIDENCE.read_text(encoding="utf-8"))
    defined = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert not any("verdict" in name.lower() for name in defined)
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "apply_candidate" in called
    assert apply_candidate.__annotations__["verdict"] == "GateVerdict"
    assert "backtest" in evaluate_candidate.__annotations__

    seen: list[GateVerdict] = []

    def refuse(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("research_only must not enter UPG-05")

    monkeypatch.setattr("pumpgrok.backtest.evidence.apply_candidate", refuse)
    provider = BacktestEvidenceProvider(_store(tmp_path))
    verdict = GateVerdict(False, "holdout_failed", "withheld")
    assert (
        provider.feed_promotion(
            object(),
            verdict,
            strategy_version_id="version-1",
            params_hash="params-1",
            apply_kwargs={},
        )
        == "withheld"
    )
    assert seen == []
