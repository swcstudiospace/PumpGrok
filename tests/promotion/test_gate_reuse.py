"""PRM-03 (criterion 6): promotion reuses the upgrade gate; it adds no second search.

A stage advance calls upgrade.gate.evaluate_candidate exactly once, against the strategy's own
paper report. Only that module constructs an eligible verdict, and the promotion package defines no
search and imports no search entry point. A zero-loss paper record is refused before the gate runs
(D17-3). The divergence tests pin their return-gap threshold explicitly, so they do not depend on
the D7 default.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from promotion_support import (
    NOW,
    STRATEGY,
    activate,
    advance,
    paper_history,
)

from pumpgrok.backtest import divergence
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.promotion import Stage, StageRefused, current_stage
from pumpgrok.promotion import stages as stages_module
from pumpgrok.promotion.stages import paper_window

SRC = Path(__file__).resolve().parents[2] / "src" / "pumpgrok"
PROMOTION_DIR = SRC / "promotion"
GATE_MODULE = SRC / "upgrade" / "gate.py"
SEARCH_ENTRY_POINTS = frozenset({"run_search", "holdout_split", "evaluate_holdout"})
EXPLICIT_RETURN_GAP_PP = 5.0


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _paper(store: LedgerStore):
    window = paper_window(store, STRATEGY, now_ts=NOW)
    assert window is not None
    return window[1]


def test_return_gap_over_explicit_threshold_is_refused(
    store: LedgerStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(divergence, "ABSOLUTE_RETURN_GAP_PP", EXPLICIT_RETURN_GAP_PP)
    params = activate(store)
    paper_history(store, wins=1, losses=1)
    paper = _paper(store)
    backtest = replace(paper, total_return=paper.total_return + Decimal("0.06"))  # 6 pp > 5 pp
    with pytest.raises(StageRefused, match="gate refused the candidate: divergence_breach"):
        advance(store, params, backtest=backtest)
    assert current_stage(store, STRATEGY) is Stage.BACKTEST


def test_return_gap_under_explicit_threshold_passes(
    store: LedgerStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 3 pp is past the D7 default of 2 pp but under the explicit 5 pp, so the explicit value
    # governs.
    monkeypatch.setattr(divergence, "ABSOLUTE_RETURN_GAP_PP", EXPLICIT_RETURN_GAP_PP)
    params = activate(store)
    paper_history(store, wins=1, losses=1)
    paper = _paper(store)
    backtest = replace(paper, total_return=paper.total_return + Decimal("0.03"))
    advance(store, params, backtest=backtest)
    assert current_stage(store, STRATEGY) is Stage.PAPER


def test_one_advance_calls_the_gate_once(
    store: LedgerStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    original = stages_module.evaluate_candidate

    def _counting(*args, **kwargs):
        calls.append("gate")
        return original(*args, **kwargs)

    monkeypatch.setattr(stages_module, "evaluate_candidate", _counting)
    params = activate(store)
    paper_history(store, wins=1, losses=1)
    advance(store, params)
    assert calls == ["gate"]


def test_zero_loss_paper_record_is_refused_before_the_gate(
    store: LedgerStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _must_not_run(*args, **kwargs):
        raise AssertionError("the gate ran on a zero-loss paper record")

    monkeypatch.setattr(stages_module, "evaluate_candidate", _must_not_run)
    params = activate(store)
    paper_history(store, wins=3, losses=0)
    with pytest.raises(StageRefused, match="profit factor undefined"):
        advance(store, params)
    assert current_stage(store, STRATEGY) is Stage.BACKTEST


def test_promotion_package_defines_no_search() -> None:
    offenders: list[str] = []
    for path in _python_files(PROMOTION_DIR):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in SEARCH_ENTRY_POINTS:
                        offenders.append(f"{path.name}:{node.lineno}: import {alias.name}")
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and "search" in node.name.lower()
            ):
                offenders.append(f"{path.name}:{node.lineno}: def {node.name}")
    assert offenders == []


def _eligible_constructions(root: Path) -> set[Path]:
    """Every file under root that calls a constructor with promotion_eligible=True."""
    found: set[Path] = set()
    for path in _python_files(root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                value = keyword.value
                if (
                    keyword.arg == "promotion_eligible"
                    and isinstance(value, ast.Constant)
                    and value.value is True
                ):
                    found.add(path)
    return found


def test_only_the_gate_constructs_an_eligible_verdict() -> None:
    assert _eligible_constructions(SRC) == {GATE_MODULE}
