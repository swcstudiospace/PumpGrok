"""The replay-only exception to the IntentRouter, held in place by two rules.

legacy_screening's replay path calls the granted exec.place directly. The owner accepted that
as a documented replay-only exception (docs/strategies-replay-exception.md). Two rules keep it
contained:

1. Legacy placement stays in strategies/legacy.py. No other module under src/pumpgrok may
   import or reference the placement names legacy.py defines, except a replay runner listed
   in REPLAY_RUNNER_ALLOWLIST.
2. No other strategy module may reach exec.place. Strategy Intents reach it only through the
   IntentRouter.

The scan is import-based: it follows `from ... import`, module aliases and attribute access.
It does not follow getattr, importlib or names built from strings.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from pumpgrok.strategies import legacy

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "pumpgrok"
LEGACY_RELPATH = "strategies/legacy.py"
LEGACY_MODULE = "pumpgrok.strategies.legacy"
EXCEPTION_DOC = REPO / "docs" / "strategies-replay-exception.md"

#: Names legacy.py defines that place orders. Importing or referencing them is legacy placement.
LEGACY_PLACEMENT_NAMES = frozenset(
    {"_place_buy", "_placement_sink", "_replay", "run_legacy_replay"}
)

#: Names that give a strategy module access to the exec.place tool.
EXEC_PLACE_NAMES = frozenset({"PLACE_SPEC", "build_place_tool"})

#: Replay runners (paths relative to src/pumpgrok) allowed to import legacy placement.
#: Empty by decision: only legacy.py and its parity tests drive the legacy replay.
#: An entry needs an owner decision recorded in docs/strategies-replay-exception.md.
REPLAY_RUNNER_ALLOWLIST: frozenset[str] = frozenset()

Finding = tuple[str, int, str]  # (path relative to src/pumpgrok, line, reason)


def _modules(root: Path) -> Iterator[tuple[str, ast.Module]]:
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        yield rel, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _resolved_module(rel: str, node: ast.ImportFrom) -> str:
    """The absolute module an ImportFrom names, resolving relative imports from rel."""
    if node.level == 0:
        return node.module or ""
    package = ["pumpgrok", *Path(rel).parts[:-1]]
    base = package[: len(package) - (node.level - 1)]
    tail = node.module.split(".") if node.module else []
    return ".".join([*base, *tail])


def _legacy_imports(tree: ast.AST, rel: str) -> tuple[set[str], list[Finding]]:
    """The names that denote the legacy module in one module, and its placement imports."""
    found: list[Finding] = []
    legacy_handles = {LEGACY_MODULE}  # dotted names that denote the legacy module
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == LEGACY_MODULE:
                    legacy_handles.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = _resolved_module(rel, node)
            for alias in node.names:
                if module == LEGACY_MODULE and alias.name in LEGACY_PLACEMENT_NAMES:
                    found.append((rel, node.lineno, f"imports legacy.{alias.name}"))
                if module == "pumpgrok.strategies" and alias.name == "legacy":
                    legacy_handles.add(alias.asname or alias.name)
    return legacy_handles, found


def legacy_placement_findings(tree: ast.AST, rel: str) -> list[Finding]:
    """Imports of, and attribute references to, legacy placement names in one module."""
    legacy_handles, found = _legacy_imports(tree, rel)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in LEGACY_PLACEMENT_NAMES
            and ast.unparse(node.value) in legacy_handles
        ):
            found.append((rel, node.lineno, f"references legacy.{node.attr}"))
    return found


def strategy_exec_place_findings(tree: ast.AST, rel: str) -> list[Finding]:
    """Ways a strategy module can reach exec.place: its tool name, builder, or a .place() call."""
    found: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == "exec.place":
            found.append((rel, node.lineno, "names the exec.place tool"))
        elif isinstance(node, ast.ImportFrom):
            module = _resolved_module(rel, node)
            names = {alias.name for alias in node.names}
            reaches_tool = (
                module.startswith("pumpgrok.tools.exec.place")
                or bool(names & EXEC_PLACE_NAMES)
                or (module == "pumpgrok.tools.exec" and "place" in names)
            )
            if reaches_tool:
                found.append((rel, node.lineno, "imports the exec.place tool"))
        elif isinstance(node, ast.Name) and node.id in EXEC_PLACE_NAMES:
            found.append((rel, node.lineno, f"uses {node.id}"))
        elif isinstance(node, ast.Attribute) and node.attr in EXEC_PLACE_NAMES:
            found.append((rel, node.lineno, f"uses {node.attr}"))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "place"
        ):
            found.append((rel, node.lineno, "calls .place(...)"))
    return found


def legacy_placement_violations(root: Path = SRC) -> list[Finding]:
    found: list[Finding] = []
    for rel, tree in _modules(root):
        if rel == LEGACY_RELPATH or rel in REPLAY_RUNNER_ALLOWLIST:
            continue
        found.extend(legacy_placement_findings(tree, rel))
    return found


def exec_place_violations(root: Path = SRC) -> list[Finding]:
    found: list[Finding] = []
    for rel, tree in _modules(root):
        if rel.startswith("strategies/") and rel != LEGACY_RELPATH:
            found.extend(strategy_exec_place_findings(tree, rel))
    return found


def _plant(root: Path, rel: str, source: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")


def test_legacy_placement_stays_inside_legacy_and_the_allowlist() -> None:
    assert LEGACY_RELPATH in {rel for rel, _ in _modules(SRC)}, "the scan must reach legacy.py"
    assert legacy_placement_violations(SRC) == []


def test_strategies_other_than_legacy_do_not_reach_exec_place() -> None:
    assert any(rel.startswith("strategies/") for rel, _ in _modules(SRC))
    assert exec_place_violations(SRC) == []


def test_replay_runner_allowlist_names_existing_modules() -> None:
    for rel in REPLAY_RUNNER_ALLOWLIST:
        assert (SRC / rel).is_file(), f"allowlisted replay runner {rel} does not exist"


def test_planted_legacy_import_in_production_is_caught(tmp_path: Path) -> None:
    _plant(
        tmp_path,
        "supervisor/planted.py",
        "from pumpgrok.strategies.legacy import _placement_sink\n",
    )
    assert [rel for rel, _, _ in legacy_placement_violations(tmp_path)] == ["supervisor/planted.py"]


def test_planted_exec_place_in_strategy_is_caught(tmp_path: Path) -> None:
    _plant(tmp_path, "strategies/planted.py", "TOOL = 'exec.place'\n")
    assert [rel for rel, _, _ in exec_place_violations(tmp_path)] == ["strategies/planted.py"]


def test_exec_place_is_not_scoped_to_strategies(tmp_path: Path) -> None:
    _plant(tmp_path, "supervisor/sniper_seat.py", "TOOL = 'exec.place'\n")
    _plant(
        tmp_path,
        "strategies/legacy.py",
        "from pumpgrok.strategies.legacy import _placement_sink\n",
    )
    assert exec_place_violations(tmp_path) == []
    assert legacy_placement_violations(tmp_path) == []


LEGACY_CASES: list[tuple[str, str, bool]] = [
    ("supervisor/x.py", "from pumpgrok.strategies.legacy import run_legacy_replay\n", True),
    ("supervisor/x.py", "from pumpgrok.strategies import legacy\nlegacy.run_legacy_replay\n", True),
    (
        "supervisor/x.py",
        "import pumpgrok.strategies.legacy\npumpgrok.strategies.legacy._placement_sink\n",
        True,
    ),
    ("strategies/x.py", "from . import legacy as lg\nlg._place_buy\n", True),
    ("supervisor/x.py", "from ..strategies.legacy import _replay\n", True),
    ("supervisor/x.py", "from pumpgrok.strategies.legacy import LegacyScreening\n", False),
    ("supervisor/x.py", "async def _place_buy(trading, mint):\n    return None\n", False),
    ("strategies/registry.py", "from pumpgrok.strategies.legacy import LegacyScreening\n", False),
]


@pytest.mark.parametrize(("rel", "source", "flagged"), LEGACY_CASES)
def test_legacy_placement_detector_cases(rel: str, source: str, flagged: bool) -> None:
    assert bool(legacy_placement_findings(ast.parse(source), rel)) is flagged


EXEC_CASES: list[tuple[str, str, bool]] = [
    ("strategies/x.py", "from pumpgrok.tools.exec.place import build_place_tool\n", True),
    ("strategies/x.py", "from pumpgrok.tools.exec import place\n", True),
    ("strategies/x.py", "def f(t, p):\n    return t.place(p)\n", True),
    ("strategies/x.py", "TOOL = 'exec.place'\n", True),
    ("strategies/x.py", "from pumpgrok.strategies.base import Intent\n", False),
    ("strategies/x.py", "from pumpgrok.supervisor.intent_router import IntentRouter\n", False),
]


@pytest.mark.parametrize(("rel", "source", "flagged"), EXEC_CASES)
def test_exec_place_detector_cases(rel: str, source: str, flagged: bool) -> None:
    assert bool(strategy_exec_place_findings(ast.parse(source), rel)) is flagged


def test_exception_is_documented_where_the_code_points() -> None:
    doc = legacy.__doc__ or ""
    assert "REPLAY-ONLY EXCEPTION" in doc
    assert "docs/strategies-replay-exception.md" in doc
    assert EXCEPTION_DOC.is_file(), "the exception note must exist"
    note = EXCEPTION_DOC.read_text(encoding="utf-8")
    for marker in (
        "REPLAY-ONLY EXCEPTION",
        "Replay runner allowlist",
        "IntentRouter",
        "test_legacy_exception.py",
    ):
        assert marker in note, f"the exception note must mention {marker!r}"
