<<<<<<< HEAD
"""Exit rules and risk never import the Grok gateway (T-14-06 scope)."""

import pathlib

FORBIDDEN = ("pumpgrok.grok", "pumpgrok/grok", "from pumpgrok.grok", "import grok")
WATCHED = [
    pathlib.Path("src/pumpgrok/supervisor/exit_rules.py"),
    *pathlib.Path("src/pumpgrok/risk").rglob("*.py"),
    *pathlib.Path("src/pumpgrok/execution").rglob("*.py"),
]


def test_no_grok_import_in_exit_risk_execution() -> None:
    offenders = []
    for path in WATCHED:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            if token in source:
                offenders.append(f"{path}:{token}")
    assert offenders == [], offenders
=======
"""GRK-07: exits and risk never import the Grok gateway, transport, cache, budget or agents.

Transitive AST closure over the exit, watcher, risk and execution code. Every
``import`` and ``from ... import`` inside a function counts too. Importing a
child executes its parent packages, so parent ``__init__`` modules are in the
closure. No module in the closure may reach ``pumpgrok.grok``, ``pumpgrok.core.llm`` or
``pumpgrok.engine.agents``. A synthetic
package proves the walker finds a forbidden edge, so a passing run means the
walker worked.

Offline only. Pure AST and file reads; no import of the audited code.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "pumpgrok"
PACKAGE = "pumpgrok"

EXIT_ROOT_MODULES = (
    "pumpgrok.engine.exits",
    "pumpgrok.engine.watcher",
    "pumpgrok.supervisor.exit_rules",
)
EXIT_ROOT_PACKAGES = (
    "pumpgrok.risk",
    "pumpgrok.execution",
)
FORBIDDEN_PREFIXES = (
    "pumpgrok.grok",
    "pumpgrok.core.llm",
    "pumpgrok.engine.agents",
)


def _module_path(root: Path, dotted: str) -> Path | None:
    parts = dotted.split(".")
    if parts[0] != PACKAGE:
        return None
    base = root.joinpath(*parts[1:])
    as_file = base.with_suffix(".py")
    if as_file.is_file():
        return as_file
    as_pkg = base / "__init__.py"
    if as_pkg.is_file():
        return as_pkg
    return None


def _dotted_name(root: Path, path: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join([PACKAGE, *parts])


def _imports(root: Path, path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _dotted_name(root, path)
    if path.name != "__init__.py":
        package = package.rsplit(".", 1)[0]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = package.split(".")
                anchor = anchor[: len(anchor) - (node.level - 1)]
                base = ".".join([*anchor, node.module] if node.module else anchor)
            else:
                base = node.module or ""
            if base:
                found.add(base)
            for alias in node.names:
                if base:
                    found.add(f"{base}.{alias.name}")
    return found


def _with_parents(dotted: str) -> list[str]:
    parts = dotted.split(".")
    return [".".join(parts[:index]) for index in range(1, len(parts) + 1)]


def _closure(root: Path, roots: Iterable[str]) -> dict[str, set[str]]:
    """Map each reached dotted module to the modules it imports (parents included)."""
    pending = list(roots)
    graph: dict[str, set[str]] = {}
    while pending:
        dotted = pending.pop()
        if dotted in graph:
            continue
        path = _module_path(root, dotted)
        if path is None:
            continue
        targets = _imports(root, path)
        graph[dotted] = targets
        for target in targets:
            for candidate in _with_parents(target):
                if candidate not in graph and _module_path(root, candidate) is not None:
                    pending.append(candidate)
        for parent in _with_parents(dotted)[:-1]:
            if parent not in graph and _module_path(root, parent) is not None:
                pending.append(parent)
    return graph


def _package_modules(root: Path, dotted_package: str) -> list[str]:
    base = root.joinpath(*dotted_package.split(".")[1:])
    return [_dotted_name(root, path) for path in sorted(base.rglob("*.py"))]


def _forbidden_edges(root: Path, roots: Iterable[str]) -> list[tuple[str, str]]:
    graph = _closure(root, roots)
    edges: list[tuple[str, str]] = []
    for module, targets in graph.items():
        for target in targets:
            if _module_path(root, target) is None:
                continue
            if any(
                target == prefix or target.startswith(prefix + ".") for prefix in FORBIDDEN_PREFIXES
            ):
                edges.append((module, target))
    return sorted(edges)


def _exit_roots() -> list[str]:
    roots = list(EXIT_ROOT_MODULES)
    for package in EXIT_ROOT_PACKAGES:
        roots.extend(_package_modules(SRC, package))
    return roots


def test_exit_risk_execution_closure_never_reaches_grok() -> None:
    assert _forbidden_edges(SRC, _exit_roots()) == []


def test_closure_reaches_the_exit_modules_it_claims_to_cover() -> None:
    graph = _closure(SRC, _exit_roots())
    assert "pumpgrok.engine.exits" in graph
    assert "pumpgrok.engine.watcher" in graph
    assert "pumpgrok.supervisor.exit_rules" in graph
    assert any(name.startswith("pumpgrok.risk.") for name in graph)
    assert any(name.startswith("pumpgrok.execution.") for name in graph)


def test_walker_flags_a_forbidden_edge_in_a_synthetic_tree(tmp_path: Path) -> None:
    package = tmp_path / "pumpgrok"
    (package / "risk").mkdir(parents=True)
    (package / "grok").mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "risk" / "__init__.py").write_text("", encoding="utf-8")
    (package / "grok" / "__init__.py").write_text("", encoding="utf-8")
    (package / "grok" / "gateway.py").write_text("X = 1\n", encoding="utf-8")
    (package / "risk" / "limits.py").write_text(
        "def check():\n    from pumpgrok.grok.gateway import X\n    return X\n",
        encoding="utf-8",
    )

    edges = _forbidden_edges(package, ["pumpgrok.risk.limits"])

    assert edges == [("pumpgrok.risk.limits", "pumpgrok.grok.gateway")]


def test_walker_follows_relative_and_transitive_imports(tmp_path: Path) -> None:
    package = tmp_path / "pumpgrok"
    (package / "risk").mkdir(parents=True)
    (package / "shared").mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "risk" / "__init__.py").write_text("", encoding="utf-8")
    (package / "shared" / "__init__.py").write_text("", encoding="utf-8")
    (package / "shared" / "bridge.py").write_text(
        "from ..grok import transport\n", encoding="utf-8"
    )
    (package / "grok").mkdir()
    (package / "grok" / "__init__.py").write_text("", encoding="utf-8")
    (package / "grok" / "transport.py").write_text("Y = 2\n", encoding="utf-8")
    (package / "risk" / "sizing.py").write_text(
        "from pumpgrok.shared import bridge\n", encoding="utf-8"
    )

    edges = _forbidden_edges(package, ["pumpgrok.risk.sizing"])

    assert ("pumpgrok.shared.bridge", "pumpgrok.grok.transport") in edges
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
