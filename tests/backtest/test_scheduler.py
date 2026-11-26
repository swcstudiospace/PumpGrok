"""Scheduler: edge repeat does no work, autonomy gating, determinism, no-LLM."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from pumpgrok.backtest import scheduler
from pumpgrok.backtest.scheduler import Scheduler, grade_result
from pumpgrok.backtest.store import RunStore


def _runner(calls: list[str], value: str = "ok"):
    def run() -> dict[str, object]:
        calls.append(value)
        return {"value": value}

    return run


def test_repeated_edge_does_zero_work(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.jsonl")
    scheduler = Scheduler(store, autonomy_level="autonomous-paper")
    calls: list[str] = []
    first = scheduler.on_edge("dataset", "digest", "legacy_screening", "h1", _runner(calls))
    second = scheduler.on_edge("dataset", "digest", "legacy_screening", "h1", _runner(calls))
    assert first.ran is True
    assert second.ran is False
    assert second.refused is False
    assert calls == ["ok"]


def test_run_requires_autonomous_paper(tmp_path: Path) -> None:
    journal: list[dict[str, object]] = []
    scheduler = Scheduler(
        RunStore(tmp_path / "runs.jsonl"),
        autonomy_level="manual-ticket",
        journal=journal.append,
    )
    calls: list[str] = []
    outcome = scheduler.on_edge("strategy", "d", "legacy_screening", "h", _runner(calls))
    assert outcome.refused is True
    assert outcome.ran is False
    assert calls == []
    assert any("refused" in str(entry.get("kind")) for entry in journal)


def test_two_runs_are_byte_equal(tmp_path: Path) -> None:
    def build(path: Path) -> bytes:
        store = RunStore(path)
        scheduler = Scheduler(store, autonomy_level="autonomous-paper")
        calls: list[str] = []
        scheduler.on_edge("dataset", "digest", "legacy_screening", "h1", _runner(calls, "v"))
        return scheduler.store_bytes()

    assert build(tmp_path / "a.jsonl") == build(tmp_path / "b.jsonl")


def test_no_llm_client_constructible() -> None:
    tree = ast.parse(inspect.getsource(scheduler))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in getattr(node, "names", [])
    }
    banned = {"pumpgrok.core.llm", "openai", "anthropic", "httpx", "requests"}
    assert not any(name in banned for name in imported), imported
    assert not hasattr(scheduler, "GrokClient")


def test_grade_result_routes_through_grading() -> None:
    verdict = grade_result(
        {"kind": "fixture", "complete": True, "duration_days": 60.0, "gap_count": 0}
    )
    assert verdict["eligible"] is False
