"""BT-13: idempotent autonomous edges, autonomy gate, no LLM, no timer."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from pumpgrok.backtest.scheduler import Edge, run_edge
from pumpgrok.backtest.store import ResultStore
from pumpgrok.events.models import EventKind
from pumpgrok.ledger.events import NoteKind
from pumpgrok.ledger.store import SOURCES, LedgerStore
from pumpgrok.replay.clock import FixtureClock

REPO = Path(__file__).resolve().parents[2]
MODULES = (
    REPO / "src" / "pumpgrok" / "backtest" / "scheduler.py",
    REPO / "src" / "pumpgrok" / "backtest" / "store.py",
    REPO / "src" / "pumpgrok" / "backtest" / "evidence.py",
)
FORBIDDEN = ("pumpgrok.grok", "pumpgrok.core.llm")


def _edge(tmp_path: Path, digest: str = "d" * 64) -> Edge:
    return Edge(
        dataset_digest=digest,
        strategy_version_id="v" * 64,
        params_hash="p" * 64,
        dataset_dir=str(tmp_path),
        strategy_id="legacy_screening",
        kind="dataset",
    )


def _paper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pumpgrok.backtest.scheduler.read_autonomy",
        lambda _store: "autonomous-paper",
    )


def test_repeated_edge_calls_strategy_run_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def spy(edge: Edge) -> object:
        calls.append(1)
        return object()

    monkeypatch.setattr("pumpgrok.backtest.scheduler.strategy_run", spy)
    _paper(monkeypatch)
    store = ResultStore(tmp_path / "results.sqlite")
    ledger = LedgerStore(tmp_path / "ledger.sqlite")
    clock = FixtureClock(1_700_000_000.0)
    edge = _edge(tmp_path)
    assert run_edge(edge, store, ledger, clock) == "done"
    assert run_edge(edge, store, ledger, clock) == "cached"
    assert calls == [1]


def test_manual_ticket_skips_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(
        "pumpgrok.backtest.scheduler.strategy_run",
        lambda _edge: calls.append(1),
    )
    monkeypatch.setattr(
        "pumpgrok.backtest.scheduler.read_autonomy",
        lambda _store: "manual-ticket",
    )
    store = ResultStore(tmp_path / "results.sqlite")
    ledger = LedgerStore(tmp_path / "ledger.sqlite")
    ledger.read(limit=1)
    store_before = store.path.read_bytes()
    ledger_before = ledger.path.read_bytes()
    status = run_edge(_edge(tmp_path), store, ledger, FixtureClock(1_700_000_000.0))
    assert status == "skipped"
    assert calls == []
    assert store.path.read_bytes() == store_before
    assert ledger.path.read_bytes() == ledger_before


def test_modules_do_not_import_an_llm_client() -> None:
    for path in MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for name in modules:
                assert not name.startswith(FORBIDDEN), f"{path.name} imports {name}"


def test_rerun_row_bytes_are_identical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pumpgrok.backtest.scheduler.strategy_run", lambda _edge: object())
    _paper(monkeypatch)
    store = ResultStore(tmp_path / "results.sqlite")
    ledger = LedgerStore(tmp_path / "ledger.sqlite")
    clock = FixtureClock(1_700_000_000.0)
    edge = _edge(tmp_path, digest="e" * 64)
    assert run_edge(edge, store, ledger, clock) == "done"
    first = store.row_bytes(edge.key())
    assert first is not None
    assert first == store.insert_or_get(edge.key(), {"ignored": "rewrite"})
    assert run_edge(edge, store, ledger, clock) == "cached"
    assert store.row_bytes(edge.key()) == first
    assert first.encode("utf-8") == sorted_canonical(first)


def test_modules_do_not_sleep() -> None:
    for path in MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            assert name != "sleep", f"{path.name} calls sleep"


def test_publication_is_existing_journal_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kinds_before = tuple(EventKind)
    notes_before = tuple(NoteKind)
    monkeypatch.setattr("pumpgrok.backtest.scheduler.strategy_run", lambda _edge: object())
    _paper(monkeypatch)
    store = ResultStore(tmp_path / "results.sqlite")
    ledger = LedgerStore(tmp_path / "ledger.sqlite")
    edge = _edge(tmp_path, digest="f" * 64)
    assert run_edge(edge, store, ledger, FixtureClock(1_700_000_000.0)) == "done"
    notes = [
        row
        for row in ledger.read(types=["JournalNote"], limit=None)
        if isinstance(row.get("payload"), dict)
    ]
    assert len(notes) == 1
    payload = notes[0]["payload"]
    assert notes[0]["type"] == "JournalNote"
    assert payload["note_kind"] == NoteKind.verdict.value
    assert payload["source"] in SOURCES
    assert "result" in payload["text"]
    assert tuple(EventKind) == kinds_before
    assert tuple(NoteKind) == notes_before
    writer = REPO / "src" / "pumpgrok" / "backtest" / "scheduler.py"
    tree = ast.parse(writer.read_text(encoding="utf-8"))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "run_journal_append" in called


def sorted_canonical(body: str) -> bytes:
    return json.dumps(json.loads(body), sort_keys=True, separators=(",", ":")).encode("utf-8")
