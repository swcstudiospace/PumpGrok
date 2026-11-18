"""PRM-05, criterion 8: the promotion package has no timer and no model call.

The evaluator runs on an injected ledger row and writes at most one stage row per event. The
forbidden spellings are assembled from parts, so this file never matches the criterion 8 grep.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable
from pathlib import Path

import pytest
from promotion_support import CLOSED_AT, RUN_ID, STRATEGY, activate, paper_history, search_for

import pumpgrok.promotion as promotion_package
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.promotion.evaluator import (
    EVALUATOR_BY,
    PromotionEvaluator,
    PromotionEvidence,
)
from pumpgrok.promotion.stages import paper_window, stage_rows
from pumpgrok.promotion.thresholds import load_thresholds
from pumpgrok.upgrade.bounds import load_bounds
from pumpgrok.upgrade.params import ParamSet

PACKAGE_DIR = Path(promotion_package.__file__).resolve().parent
_SLEEP_CALL = "clock" + ".sleep"
_GROK_MODULE = "pumpgrok" + ".grok"
_TIMER_MODULES = frozenset({"asyncio", "threading", "sched", "signal", "time"})
_TIMER_NAMES = frozenset({"sleep", "Timer", "call_later", "call_at"})


def _package_sources() -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in sorted(PACKAGE_DIR.glob("*.py"))}


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def test_package_text_has_no_timer_call_or_model_module() -> None:
    for path, text in _package_sources().items():
        assert _SLEEP_CALL not in text, path.name
        assert _GROK_MODULE not in text, path.name


def test_package_imports_no_timer_or_model_module() -> None:
    for path, text in _package_sources().items():
        for module in _imported_modules(ast.parse(text)):
            assert module.split(".")[0] not in _TIMER_MODULES, f"{path.name} imports {module}"
            assert not module.startswith(_GROK_MODULE), f"{path.name} imports {module}"


def test_package_calls_no_timer_function() -> None:
    for path, text in _package_sources().items():
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.Name):
                name = node.id
            else:
                continue
            assert name not in _TIMER_NAMES, f"{path.name}:{node.lineno} uses {name}"


def test_handler_is_synchronous() -> None:
    assert not inspect.iscoroutinefunction(PromotionEvaluator.handle)


def _evaluator(store: LedgerStore, params: ParamSet, calls: list[str]) -> PromotionEvaluator:
    """An evaluator whose evidence is the strategy's own window, recorded in calls."""

    def evidence(strategy_id: str) -> PromotionEvidence:
        calls.append(strategy_id)
        return PromotionEvidence(
            params=params,
            bounds=load_bounds(),
            search=search_for(params),
            run_id=RUN_ID,
            backtest=paper_window(store, strategy_id, now_ts=CLOSED_AT)[1],
        )

    source: Callable[[str], PromotionEvidence] = evidence
    return PromotionEvaluator(store, evidence=source, thresholds=load_thresholds())


def _last(store: LedgerStore, row_type: str) -> dict:
    return store.read(types=[row_type], limit=None)[-1]


def test_trigger_row_writes_one_stage_row(store: LedgerStore) -> None:
    params = activate(store)
    paper_history(store, wins=1, losses=1)
    calls: list[str] = []

    row = _evaluator(store, params, calls).handle(_last(store, "PositionClosed"))

    assert row is not None
    assert row["payload"]["to_stage"] == "PAPER"
    assert row["payload"]["by"] == EVALUATOR_BY
    assert len(stage_rows(store, STRATEGY)) == 1
    assert calls == [STRATEGY]


def test_non_trigger_row_writes_nothing_and_asks_no_evidence(store: LedgerStore) -> None:
    params = activate(store)
    paper_history(store, wins=1, losses=1)
    calls: list[str] = []

    assert _evaluator(store, params, calls).handle(_last(store, "PositionOpened")) is None

    assert stage_rows(store, STRATEGY) == []
    assert calls == []


def test_repeated_trigger_writes_no_second_row(store: LedgerStore) -> None:
    params = activate(store)
    paper_history(store, wins=1, losses=1)
    evaluator = _evaluator(store, params, [])
    trigger = _last(store, "PositionClosed")
    assert evaluator.handle(trigger) is not None

    assert evaluator.handle(trigger) is None

    assert len(stage_rows(store, STRATEGY)) == 1


def test_writer_must_be_human_or_gate(store: LedgerStore) -> None:
    with pytest.raises(ValueError, match="writer"):
        PromotionEvaluator(
            store,
            evidence=lambda _strategy: None,
            thresholds=load_thresholds(),
            by="desk:auto",
        )
