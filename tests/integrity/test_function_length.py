"""Function-length guard for the INT-08 stage split (INT-08).

``_place_buy`` and ``_place_order`` (execution/paper_adapter/buy.py) plus
``_replay_cycles`` (supervisor/scheduler/replay_cycles.py) were split into stage
functions with unchanged public signatures and no behavior change. This
module pins the split: each orchestrator is at most 60 lines (AST span,
``end_lineno - lineno``), and the extracted stage functions still exist.

Deterministic; no network.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "pumpgrok"

_MAX_LINES = 60

_ORCHESTRATORS = {
    "execution/paper_adapter/buy.py": ("_place_buy", "_place_order"),
    "supervisor/scheduler/replay_cycles.py": ("_replay_cycles",),
}

_STAGES = {
    "execution/paper_adapter/buy.py": (
        "_order_risk_decision",
        "_order_curve",
        "_buy_sizing",
        "_buy_append_batch",
        "_buy_confirm",
        "_buy_fill_rows",
        "_buy_settle",
    ),
    "supervisor/scheduler/replay_cycles.py": (
        "_replay_chief",
        "_replay_scout",
        "_replay_mark_open",
        "_replay_risk",
        "_replay_whale",
        "_replay_sniper",
        "_replay_rug",
        "_replay_exit",
        "_replay_shill",
        "_replay_signal",
        "_replay_journal",
    ),
}


def _function_spans(path: Path) -> dict[str, int]:
    """AST span (``end_lineno - lineno``) per function name in one file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    spans: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            spans[node.name] = node.end_lineno - node.lineno
    return spans


def test_orchestrators_fit_length_budget() -> None:
    """Each split orchestrator is at most 60 lines."""
    for rel, names in _ORCHESTRATORS.items():
        spans = _function_spans(SRC / rel)
        for name in names:
            assert name in spans, f"{name} missing from {rel}"
            assert spans[name] <= _MAX_LINES, f"{name} spans {spans[name]} lines (max {_MAX_LINES})"


def test_stage_functions_exist() -> None:
    """The extracted stages were not folded back into the orchestrators."""
    for rel, names in _STAGES.items():
        spans = _function_spans(SRC / rel)
        for name in names:
            assert name in spans, f"stage {name} missing from {rel}"
