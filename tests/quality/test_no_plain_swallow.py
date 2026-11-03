"""QLT-06: a guard rejects new plain-swallow broad excepts in src/pumpgrok (CONTEXT 11-05).

A plain swallow is a handler that catches a broad type (bare except, Exception, BaseException, or
a tuple holding one of them) and whose body neither re-raises nor calls anything: no log line, no
cleanup, no typed error. The six hotspot swallows were narrowed to typed error tuples; the handlers
below predate the guard and are recorded as a shrink-only baseline keyed by file and enclosing
function. Adding a handler fails the test. Fixing one also fails until its entry is removed, so the
baseline can only go down.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "pumpgrok"
BROAD_TYPES = frozenset({"Exception", "BaseException"})

BASELINE: Counter[tuple[str, str]] = Counter(
    {
        ("supervisor/health.py", "_method_of"): 1,
        ("supervisor/health.py", "_path_of"): 1,
        ("supervisor/lifecycle.py", "_notify_stopped"): 1,
        ("supervisor/scheduler/degraded.py", "kill_switch_engaged"): 1,
        ("supervisor/scheduler/serve.py", "_snapshot"): 1,
        ("supervisor/scheduler/supervisor.py", "autonomy_level"): 1,
        ("supervisor/scheduler/supervisor.py", "ready"): 1,
        ("supervisor/seat_task.py", "_latch_unreadable_ledger"): 1,
        ("tools/onchain/priority_fee.py", "estimate_priority_fee"): 1,
    }
)


def _is_broad(type_node: ast.expr | None) -> bool:
    if type_node is None:
        return True
    if isinstance(type_node, ast.Name):
        return type_node.id in BROAD_TYPES
    if isinstance(type_node, ast.Tuple):
        return any(_is_broad(element) for element in type_node.elts)
    return False


def _is_plain(handler: ast.ExceptHandler) -> bool:
    for statement in handler.body:
        for node in ast.walk(statement):
            if isinstance(node, ast.Raise | ast.Call):
                return False
    return True


class _SwallowScanner(ast.NodeVisitor):
    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.stack: list[str] = []
        self.found: list[tuple[str, str]] = []

    def _enter(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _enter
    visit_AsyncFunctionDef = _enter

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if _is_broad(node.type) and _is_plain(node):
            owner = self.stack[-1] if self.stack else "<module>"
            self.found.append((self.rel, owner))
        self.generic_visit(node)


def plain_swallows() -> Counter[tuple[str, str]]:
    found: Counter[tuple[str, str]] = Counter()
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        scanner = _SwallowScanner(rel)
        scanner.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        found.update(scanner.found)
    return found


def test_no_new_plain_swallow_handlers() -> None:
    new = plain_swallows() - BASELINE
    assert not new, f"new plain-swallow broad excepts (narrow them or log and re-raise): {new}"


def test_baseline_entries_are_removed_once_their_handler_is_fixed() -> None:
    fixed = BASELINE - plain_swallows()
    assert not fixed, f"remove fixed entries from BASELINE to ratchet it down: {fixed}"
