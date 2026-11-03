"""QLT-04: no function over 60 lines in the successors of the six hotspots (CONTEXT 11-05).

The successors are the modules the splits created or kept: the paper_adapter package (sell,
batch and confirm with their stage modules, plus buy and marks), the RiskEngine evaluate
modules, the cli backtest modules, the config settings and sections, and the seat_task family.
A function's length counts from its first decorator (or its def line) to its last line.
No allowlist exists: a function over the limit fails this test.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "pumpgrok"
MAX_FUNCTION_LINES = 60

SUCCESSOR_GLOBS = (
    "execution/paper_adapter/*.py",
    "risk/engine/*.py",
    "cli/backtest*.py",
    "config/settings.py",
    "config/sections/*.py",
    "supervisor/seat_*.py",
)

HOTSPOT_SUCCESSORS = (
    "execution/paper_adapter/sell.py",
    "execution/paper_adapter/sell_stages.py",
    "execution/paper_adapter/batch.py",
    "execution/paper_adapter/batch_stages.py",
    "execution/paper_adapter/confirm.py",
    "execution/paper_adapter/confirm_stages.py",
    "risk/engine/core.py",
    "risk/engine/rules.py",
    "cli/backtest.py",
    "cli/backtest_holdout.py",
    "cli/backtest_paper_gate.py",
    "config/settings.py",
    "config/sections/core.py",
    "supervisor/seat_task.py",
    "supervisor/seat_restart.py",
    "supervisor/seat_relay.py",
)


def successor_files() -> list[Path]:
    found = {path for pattern in SUCCESSOR_GLOBS for path in SRC.glob(pattern)}
    return sorted(found)


def function_lengths(path: Path) -> list[tuple[int, str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rows: list[tuple[int, str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            start = min([node.lineno, *(dec.lineno for dec in node.decorator_list)])
            assert node.end_lineno is not None
            rows.append((node.end_lineno - start + 1, node.name, node.lineno))
    return rows


def test_every_hotspot_successor_is_in_the_guarded_set() -> None:
    guarded = {path.relative_to(SRC).as_posix() for path in successor_files()}
    missing = sorted(set(HOTSPOT_SUCCESSORS) - guarded)
    assert not missing, f"successor modules outside the guard: {missing}"


def test_every_hotspot_successor_exists() -> None:
    absent = [rel for rel in HOTSPOT_SUCCESSORS if not (SRC / rel).is_file()]
    assert not absent, f"successor modules missing from src: {absent}"


def test_no_successor_function_exceeds_sixty_lines() -> None:
    over: list[str] = []
    for path in successor_files():
        for length, name, lineno in function_lengths(path):
            if length > MAX_FUNCTION_LINES:
                rel = path.relative_to(SRC).as_posix()
                over.append(f"{rel}:{lineno} {name} is {length} lines")
    assert not over, "functions over 60 lines in hotspot successors:\n" + "\n".join(over)
